# R107-E — Decode oproj output-row amortisation (H-OPROJ-ISSUE)

Student: maple-alphonse · PR #644 · branch `maple-alphonse/r107-decode-oproj-amortisation`
Assignment `maple-r107-e-decode-oproj-amortisation`, revision `r107-e-rev1`
`BASE_SHA = 2454cc01ea3afabac067f0a271e36901fea7d21c`
Host: Apple **M4 Pro**, 20 GPU cores / 14 CPU / 48 GiB, macOS 26.5.2 (25F84),
Apple GPU generation **16** ⇒ `nax_available = false`, kernel family
`applegpu_g16s`. **Zero official submissions were dispatched from this PR.**

---

## §0 — Verdict

**PENDING — filled after sessions `abba1` + `abba2` land.**

### Mandatory caveats carried into the verdict

- **§B.0.6 α/β degeneracy.** Every M5-projected microsecond in this report
  inherits the two-parameter degeneracy recorded at
  `research/CURRENT_RESEARCH_STATE.md:1757`: `α ≈ 0.389` (M5 ceiling 686 GB/s,
  pool efficiency ≈ 0.86) and `α ≈ 0.437` (ceiling 610.6 GB/s, efficiency
  ≈ 0.62) fit the existing corpus equally well, differ by ~12 % in every M5
  headroom figure, and imply *opposite* research programmes — under the first,
  per-family efficiency work pays; under the second, only compulsory-byte
  reductions pay. R107-E is a direct empirical probe of that fork, because its
  arms move **zero** compulsory bytes (see §3). The named resolving experiment
  remains: run `research/fern_r101_bw_probe.swift` on the official M5 (~7 s,
  no submission-surface change).
- **M5 provenance label (carried verbatim as instructed):**
  `α = 0.4369 / β = 0.5 two-pool map, residual −6.63 %, #561`
- **Rule 98.9.** Every byte-count improvement reported here is
  **cache-resident issue-side traffic, not DRAM traffic.** The compulsory DRAM
  footprint is bit-identical across all four arms (§3, `weight_code_reread_factor
  = 1.0` in every arm). No figure in this report headlines a cache-resident
  number as a bandwidth saving.

---

## §1 — Hypothesis and lever

**H-OPROJ-ISSUE.** The decode NVFP4 gated-affine oproj family — T3b
`oproj_act_h64` (30 calls/step) and T3c `oproj_act_h48` (10 calls/step) —
re-issues cache-resident activation and scale traffic once per output row. With
the shipped geometry each simdgroup produces only `results_per_simdgroup = 4`
output rows, so one pass over the activation vector is amortised over just 4
rows. Raising output rows per simdgroup should cut issued activation traffic
proportionally.

The lever is the generator's threadgroup geometry in
`lagunaGatedAffineOProjNVFP4Source` plus the matching launcher grid in the
lane-major branch of `lagunaGatedAffineOProjNVFP4`. Nothing else changes: the
same arithmetic, the same accumulation order per output row, the same weight
layout, the same dequantisation path.

### Arm table (2×2 factorial)

| id | `num_simdgroups` | `results_per_simdgroup` | rows/TG | threads/TG | TGs | grid threads | role |
|---|---:|---:|---:|---:|---:|---:|---|
| g0 | 2 | 4 | 8 | 64 | 256 | 16384 | shipped baseline |
| g1 | 2 | 8 | 16 | 64 | 128 | 8192 | 2× amortisation |
| g2 | 1 | 8 | 8 | 32 | 256 | 8192 | 2× amortisation, TG count preserved |
| g3 | 4 | 4 | 16 | 128 | 128 | 16384 | **negative control** |

The design is a clean 2×2:

- **Factor A — `results_per_simdgroup` 4→8** (the amortisation factor itself):
  A+ = {g1, g2}, A− = {g0, g3}.
- **Factor B — `rows_per_threadgroup` 8→16** (threadgroup shape):
  B+ = {g1, g3}, B− = {g0, g2}.
- **Interaction AB:** + = {g0, g1}, − = {g2, g3}.

g3 is the negative control: it doubles rows per *threadgroup* without touching
rows per *simdgroup*, so it changes threadgroup shape while leaving the
amortisation factor at 4. If g3 moves as much as g1, the effect is threadgroup
shape, not amortisation.

**Known confound, stated up front.** Because rows/TG × TGs is fixed by `out_vec`,
raising `results_per_simdgroup` necessarily halves total grid threads
(16384 → 8192). Factor A is therefore confounded with total thread count and
hence with memory-level parallelism. The 2×2 cannot separate them; §6 names the
cheap fifth arm that can.

### Preregistered outcomes

`V-AMORT` · `N-AMORT` · `V-TGSHAPE` · `N-ISSUE-BOUND` · `N-ROOFLINE` ·
`N-CORRECT` · `N-BUILD`. One is selected in §0.

### Shippability bar

A lever is shippable only at ≥ **0.4 % relative** decode improvement with a CI
excluding zero. On M5 that is **26 µs/step** against `cs` ≈ 6.5 ms. On this
host, whose measured g0 decode step is ~13.08 ms, the equivalent absolute bar is
**52.3 µs/step**.

---

## §2 — Paired in-situ timing

**PENDING — sessions `abba1` + `abba2`.**

### Stage 1 — unpaired four-arm screen (session `screen1`, confounded)

`PRECOOL_SECONDS=0`, positions 1–4, 189–214 s per arm.

| pos | arm | decode s/tok | Δ vs g0 | prefill s/tok (placebo) | correctness |
|---:|---|---:|---:|---:|---|
| 1 | g0 | 0.01307970 | — | 0.00114136 | pass |
| 2 | g1 | 0.01318088 | +0.774 % | 0.00114368 | pass |
| 3 | g2 | 0.01314602 | +0.507 % | 0.00115303 | pass |
| 4 | g3 | 0.01310971 | +0.229 % | 0.00115371 | pass |

Two things follow immediately and are not confounded:

1. **All four arms pass local correctness.** `N-CORRECT` and `N-BUILD` are
   ruled out. Every arm builds through `./benchmark.sh --local-iterate` and
   produces matching greedy tokens locally.
2. **The screen is uninterpretable on speed.** The placebo prefill channel —
   which is *provably* identical code across arms (§4) — drifts +1.08 % across
   positions 1→4, about 0.36 % per position. That drift is the same size as the
   decode deltas being measured. Directionally all three candidates are slower
   than shipped, but a serial four-arm screen cannot establish that.

Stage 1 is reported as a build/correctness screen only. The speed claim rests
entirely on the ABBA-paired sessions.

### Between-session noise floor

`abba1.p01.g0` decode = 0.0132137 versus `screen1.p01.g0` decode = 0.0130797:
the **same arm at the same schedule position in two sessions differs by ~1 %**,
which is 2.5× the shippability bar. This is why nothing in §2 is estimated
across sessions; all contrasts are within-session, within-half.

---

## §3 — Issued-traffic model (Rule 98.9: cache-resident, not DRAM)

`research/maple-alphonse-r107e-traffic-model.py` →
`research/artifacts/maple-alphonse-r107e/geom-traffic-model.json`. All
structural assertions pass.

T3b `oproj_act_h64` (`in_vec = 8192`, `out_vec = 2048`, `k_blocks = 16`),
g0 → g1/g2:

| quantity | g0 | g1 / g2 | Δ |
|---|---:|---:|---:|
| issued activation bytes | 8.913 MB | 4.456 MB | −50.0 % |
| issued total bytes | 18.416 MB | 13.959 MB | **−24.2 %** |
| issued / compulsory | 2.124 | 1.610 | — |
| activation re-read factor | 544× | 272× | −50.0 % |
| ops per useful FMA | 1.891 | 1.633 | −13.6 % |
| **`weight_code_reread_factor`** | **1.000** | **1.000** | **0** |

T3c `oproj_act_h48`: issued total 13.828 → 10.486 MB (−24.2 %), same ratios.

**The load-bearing row is the last one.** `weight_code_reread_factor` is exactly
1.0 in every arm, so the compulsory DRAM byte count is *identical* across g0,
g1, g2 and g3. The 24.2 % is issued-instruction / cache-resident traffic only.
Under the pessimistic branch of the α/β fork (§0), a change that moves zero
compulsory bytes is predicted to move zero time.

**Static IR is flat and is not evidence of amortisation.** The AIR census (§4)
shows instruction-*site* counts essentially unchanged across arms because the
`k_blocks` loop is not unrolled. Those are static counts, not dynamic issue
counts. They are reported for completeness and are **not** used as amortisation
arithmetic.

**Named risk.** `results_per_simdgroup = 8` halves grid threads 16384 → 8192,
i.e. 256 simdgroups. On a 40-core M5 Max that is ~6.4 simdgroups per core, which
may under-supply memory-level parallelism. On this 20-core M4 Pro the same arm
gets ~12.8 simdgroups per core, so **this host is structurally more forgiving to
g1/g2 than the ranked M5 is.** A local null is therefore not weaker evidence
than an M5 null would be; a local win would need M5 confirmation.

---

## §4 — Offline AIR census, and why "env unset" is a sound baseline

`research/maple-alphonse-r107e-oproj-geom-census.py` →
`research/artifacts/maple-alphonse-r107e/geom-air-ledger.json` plus
`oproj_g{0..3}_h{48,64}.metal` / `.ir` / `.compile.log`.

All 8 arm × head variants compile cleanly under
`xcrun metal -std=metal4.0 -fno-fast-math`.

The decisive result:

```
g0_emission_identical_to_base = { h48: true, h64: true }
```

The parameterisation is a **provable byte-for-byte no-op for the shipped arm**.
That licenses using "`DARKBLOOM_OPROJ_GEOM` unset" as the paired baseline from a
single build, instead of rebuilding at `BASE_SHA` between arms — which would
otherwise have doubled session length and injected build-order confounds.

### Built-in placebo channel

The decode oproj call site is gated on `gatePerHead && B == 1 && L == 1`
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:6355-6362`). The 512-token
prefill pass therefore **cannot reach this kernel under any arm**. Prefill is
identical machine code in all four arms, so the prefill channel is a free
same-session, same-schedule estimate of the measurement noise floor and drift.
Every decode contrast in §2 is reported alongside the same estimator applied to
prefill. A decode effect that is not larger than its prefill twin is not an
effect.

---

## §5 — Roofline: how much money is actually in this family

Anchored on `research/artifacts/fern-r106g/family_breakdown.json`
(`B_step = 1,671,402,432 B`) and `research/artifacts/fern-r101/m5-pool-table.csv`.
Measured M4 Pro bandwidth ceiling **266.80 GB/s** (fern-r101 corollary 3, which
retires the earlier 273 / 266.3 / 260.6 / 237.4 candidates).

| family | calls | MB/step | % of `B_step` | M4 µs measured | µs/dispatch | M4 GB/s | % of ceiling | headroom vs lmhead | vs dense_down | M5 µs modelled |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| T3b oproj h64 | 30 | 259.584 | 15.531 | 1117.7 | 37.257 | 232.25 | **87.05** | 118.8 µs | 82.6 µs | 488.376 (16.279/disp) |
| T3c oproj h48 | 10 | 64.901 | 3.883 | 301.8 | 30.180 | 215.05 | **80.60** | 52.0 µs | 43.0 µs | 131.871 (13.187/disp) |

### Both Rule-81 reference rates, as required

- **lmhead reference** — 97.4 % of peak. Family total headroom = **170.8 µs =
  1.306 %** of the local decode step.
- **dense_down reference** — 94.0 % of peak. Family total headroom = **125.7 µs
  = 0.961 %** of the local decode step.

`dense_down` is the fairer reference: it is the same quantised-GEMV access
pattern, whereas lmhead is an unusually favourable dense case. Under the fairer
reference the family's *entire* remaining inefficiency is 0.961 % of decode.

**What that means for the bar.** Clearing the 52.3 µs local bar requires
capturing **30.6 %** (lmhead) to **41.6 %** (dense_down) of the family's entire
remaining bandwidth deficit — from a change that reduces zero compulsory bytes.
Whole-step local achieved bandwidth is 127.79 GB/s = **47.9 %** of ceiling, so
the step as a whole is far from the wall even though this family is at 87 % / 81 %.

Rule-81's ≥10 pp-below-reference clause is **met under lmhead and fails under
the fairer dense_down**; the ≥30 µs clause holds under both. This is stated
explicitly rather than reporting only the flattering reference.

This block also retires an inconsistency flagged during review: a "0.45
µs/dispatch" figure circulating for this family is wrong by ~80×. The measured
value on this host is **37.26 µs/dispatch** (T3b), 16.28 µs modelled for M5.

### Deconfliction table

| owner | PR | reserved token | line at base | touched by R107-E? |
|---|---|---|---:|---|
| edward | #629 | `lagunaDecodeNVFP4QKVLaneMajorSource` | 4963 | **no** |
| edward | #629 | `lagunaRoutedSwiGLUQMVPackedTop8` | 8071 | **no** |
| tanjiro | #642 | `laguna_sliding_fused_attn_ring_v1` | 1508 | **no** |
| tanjiro | #642 | `laguna_full_fused_attn_grow_v1` | 2028 | **no** |
| maple-alphonse | #644 | `lagunaGatedAffineOProjNVFP4Source` + lane-major launcher | 4358–4359, 4624 | yes (this PR) |

**Line-shift disclosure.** My edit inserts 41 net lines below line 4358, so
every reserved anchor at or below that point shifts by **+41 lines** in this
branch. **Zero reserved tokens are modified** — the shift is positional only,
and a rebase or three-way merge resolves it without content conflict. The
reserved sites at 4963 and 8071 relocate to 5004 and 8112 in this branch's HEAD;
their text is byte-identical to base.

**Permitted extension, not exercised unless the mechanism is proven on oproj:**
T2d `routed_shared_nvfp4_down_residual` at `:8273/:8274`, `:8299/:8300`,
`:8470/:8471`, `:8599/:8600`.

---

## §6 — Motivating prior #308, and its disjointness from this experiment

**#308** (tanjiro, round 83) is the motivating precedent that a pure
threadgroup/packing geometry flip can be worth real time: the L3 packing default
flip (`research/tanjiro_packing_default_flip.patch`) measured
**−36.9 µs/step = +0.562 % of `cs`**, CI [−61.0, −12.9] µs = [+0.196 %,
+0.929 %]. References: `research/CURRENT_RESEARCH_STATE.md:2667, :3435, :5385,
:5406, :5426`; `research/RESEARCH_ARCHIVE_through-round-91.md:161, :168, :981`.

**Disjointness.** #308 acts on the routed SwiGLU / L3 packing site; it changes
which packing default that site selects. R107-E acts only on
`lagunaGatedAffineOProjNVFP4Source` and the lane-major branch of its launcher.
The two edits share no generator, no kernel, no launcher, and no reserved token,
and #308's measured gain is neither assumed by nor at risk from this experiment.
#308 is cited as evidence that the *class* of lever can pay, not as a component
of R107-E's effect.

The complementary prior is **#48**, which measured the 8× threadgroup collapse
at −0.1488 % — i.e. the same class of lever can also be a small *loss*. The
archive additionally records that threadgroup geometry **can change sign across
core counts**, which is exactly why §3 names the 20-core versus 40-core
simdgroups-per-core asymmetry, and why an M4 result on this lever is
directional evidence about mechanism rather than a rankable verdict.

---

## §7 — Method and reproduction

### Instrument

Commit `f82466c7`, **+49 / −8 lines, single file**
`Sources/MLXFastModel/LagunaRuntimeModel.swift`. Diff = 5,532 bytes (bar:
8 KiB). File 386,006 B versus base 384,245 B ⇒ growth 1,761 B.

1. `lagunaGatedAffineOProjNVFP4Source` gains
   `numSimdgroups: Int = 2, resultsPerSimdgroup: Int = 4`; the two
   `constexpr uint results_per_simdgroup / num_simdgroups` lines (4358/4359)
   interpolate them. Those two exact lines also occur at 3991, 5113 and 5294 for
   *other* kernels, so the edit had to be line-targeted rather than textual.
2. `resultZeros` sizes the `thread float result[...]` initialiser.
3. `struct LagunaOProjGeometry` with `.shipped = (2, 4, "")`, plus
   `lagunaOProjGeometry` resolving `DARKBLOOM_OPROJ_GEOM` ∈
   {`g1`→(2,8,"_g1"), `g2`→(1,8,"_g2"), `g3`→(4,4,"_g3")}, default `.shipped`.
   The tag is appended to the pipeline name so arms cannot collide in the
   pipeline cache.
4. Geometry is applied **only** to `lagunaActivatedOProjLaneMajorKernels`, the
   live dictionary. The three unused dictionaries deliberately stay at shipped
   defaults: the non-`preActivatedGate` `gateSetup` uses `if (lid < gate_heads)`
   plus a threadgroup barrier and would be *wrong* at 32 threads (g2), which
   would have produced a spurious `N-CORRECT`.
5. Launcher lane-major branch (`:4624`):
   `let geom = gateIsActivated ? lagunaOProjGeometry : .shipped`, grid
   `((outVec / geom.rowsPerThreadgroup) * geom.threadsPerThreadgroup, 1, 1)`,
   threadgroup `(geom.threadsPerThreadgroup, 1, 1)`. For g0 this is exactly the
   former 16384 / 64. The non-lane-major launcher is untouched.

### Driver

`research/maple-alphonse-r107e-insitu.sh`. Per arm: sleep precool →
`./benchmark.sh --local-cool-gate-only` → `rm -f score.local-iterate.json` →
run with `DARKBLOOM_OPROJ_GEOM` set (unset for g0) →
`git checkout -- Package.resolved` → copy `.score.json` → emit
`<session>.p<NN>.<arm>.row.json`.

```bash
SESSION=abba1 \
SCHEDULE="g0 g1 g2 g3 g3 g2 g1 g0 g0 g1 g2 g3 g3 g2 g1 g0" \
PRECOOL_SECONDS=120 MAX_CONSECUTIVE_FAILURES=2 \
bash research/maple-alphonse-r107e-insitu.sh
# repeat with SESSION=abba2, identical schedule
python3 research/maple-alphonse-r107e-analyse.py abba1 abba2
python3 research/maple-alphonse-r107e-traffic-model.py <paired g0 decode s/tok>
python3 research/maple-alphonse-r107e-wandb.py
```

Each session is 4 ABBA blocks of `g0 g1 g2 g3 | g3 g2 g1 g0`, giving 8 halves
and 8 observations per arm across two sessions — **8 ABBA pairs per contrast, 4
forward-order and 4 reverse-order**, satisfying the order-reversal requirement.
`analyse.py` refuses any row with `passed != true`, estimates within-half so
session and thermal drift cancel to first order, and reports per-order means so
residual order effects are visible rather than absorbed.

### Instrument revert

The instrument is reverted to base before the final commit unless a lever clears
the bar. Proof of revert:

```
git diff --numstat 2454cc01 HEAD -- Sources/ Vendor/ benchmark.json
```

**PENDING — final numstat pasted here after revert.**

---

## §8 — Handoff payload for fern (#625)

Paste-ready:

```text
FROM: maple-alphonse R107-E (PR #644), decode oproj output-row amortisation
TO:   fern (#625)

MEASURED ON THIS HOST (Apple M4 Pro, 20 GPU cores, gen 16, nax_available=false):
  ceiling_gb_per_s                266.80   (fern-r101 corollary 3; retires 273 / 266.3 / 260.6 / 237.4)
  B_step_bytes                    1671402432  (fern-r106g family_breakdown.json)
  local_decode_step_us            13079.7
  local_whole_step_gb_per_s       127.79   (47.9 % of ceiling)

  T3b oproj_act_h64: 30 calls, 259.584 MB/step (15.531 % of B_step),
                     1117.7 us, 37.257 us/dispatch, 232.25 GB/s = 87.05 % of ceiling
  T3c oproj_act_h48: 10 calls,  64.901 MB/step ( 3.883 % of B_step),
                      301.8 us, 30.180 us/dispatch, 215.05 GB/s = 80.60 % of ceiling

  family_headroom_us   lmhead_ref=170.8 (1.306 % of decode) | dense_down_ref=125.7 (0.961 %)
  NOTE: a "0.45 us/dispatch" figure for this family is wrong by ~80x. Use 37.26 (T3b) / 30.18 (T3c).

STRUCTURAL RESULT (arm-invariant, no timing dependency):
  weight_code_reread_factor == 1.000 in ALL FOUR geometry arms
  => compulsory DRAM bytes are IDENTICAL across arms; all arm deltas are
     cache-resident issue-side (Rule 98.9). Any measured time delta here is
     therefore direct evidence on the alpha/beta fork.

ALPHA/BETA FORK (CURRENT_RESEARCH_STATE B.0.6, :1757):
  alpha ~ 0.389 (ceiling 686, eff ~0.86) => per-family efficiency work pays
  alpha ~ 0.437 (ceiling 610.6, eff ~0.62) => only compulsory bytes pay
  R107-E outcome and its bearing on this fork: SEE §0 OF THE R107-E REPORT.
  Provenance label carried verbatim: alpha = 0.4369 / beta = 0.5 two-pool map,
  residual -6.63 %, #561
  RESOLVING RUN STILL OPEN: research/fern_r101_bw_probe.swift on the official M5
  (~7 s, zero submission-surface change). This is the cheapest single action
  that collapses the degeneracy.

PLACEBO CHANNEL YOU CAN REUSE:
  Decode oproj is gated on gatePerHead && B==1 && L==1
  (LagunaRuntimeModel.swift:6355-6362), so 512-token prefill cannot reach it.
  Prefill is a free identical-code noise-floor channel for any oproj-only arm.
  Observed drift on an unpaired 4-position serial screen: +1.08 % over 4
  positions (~0.36 %/position). Unpaired serial screens at the 0.4 % bar are
  therefore not interpretable on this host.

  Between-session same-arm same-position spread: ~1 % (2.5x the 0.4 % bar).
  Use within-session ABBA halves.
```

---

## § Reply to advisor

**PENDING — filled with the §0 verdict.**
