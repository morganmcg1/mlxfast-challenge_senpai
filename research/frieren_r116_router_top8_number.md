# R116-A §0P.23 — the router top-8 number

**Deliverable requested (advisor comments 6 & 7, 04:37Z / 04:40Z):** µs/step and
% of DRAM peak for the decode router top-8 kernel at SPLIT=1, from a warmed
isolated 39-layer decode chain, plus one line naming which variant the build
actually selects. Alphonse is gated on this.

**Answer, in one line:**
`prefill_router_tournament_ordinal_norm_active64_v2` —
**186.263 ± 0.214 µs/step** (n=8, sd 0.605), **4.775 ± 0.006 µs/call × 39
calls/step**, **2.1775 ± 0.0037 %** of the 8557 µs SPLIT=1 busy sum, and
**≈0.12 % of DRAM peak**. This is *not* below the atlas's own resolution: the
row is measured ~870× above its own noise floor.

---

## 1. Which variant the build selects

**`prefill_router_tournament_ordinal_norm_active64_v2`** — the *normalizing*
variant. This is an observation, not an inference from the gate reads: it is the
kernel name that actually appears in the profile atlas, and it is the **only**
router-tournament name that appears. There is no non-`norm` `..._active64_v2`
row, and none of the `_v3` / `_norm_v2` / bare `_ordinal_*` fallback names
appear in any of the 14 runs.

This confirms the advisor's static reading end to end: all three gates default
ON (`!= "0"`), so `lagunaDecodeRouterTop8` takes the **first** branch at
`LagunaRuntimeModel.swift:9729`, not the `_v3` fallback at `:9745`, and
`normalizing` is true.

## 2. The measurement and where it comes from

No new GPU time was needed. The number was already captured, committed, and in
exactly the requested regime.

**Source:** `research/r87a-runs/ceiling/` — tanjiro's r87a ceiling atlas, 14
runs, reference arm `A0`, 8 `A0` replicates.

**Regime is the requested one, verified not assumed:**
`research/tanjiro-r87a-campaign.sh:64` sets
`DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1`. Every steady-step line
in the logs reads `cbs=406.0 dispatches=406.0` — one command buffer per
dispatch, and `gpu_busy_sum == gpu_busy_union` to within 1 µs, which is the
SPLIT=1 signature (no dispatch can overlap another).

Warmed and isolated as requested: 199–200 steady decode steps after a seed
forward, first-step warmup excluded, 39-layer chain, teacher-forced with
`0 divergences (all match)`.

| quantity | mean | sd | sem | n |
|---|---|---|---|---|
| router top-8 µs/step | **186.263** | 0.605 | 0.214 | 8 |
| router top-8 µs/call | **4.775** | 0.017 | 0.006 | 8 |
| share of busy_sum | **2.1775 %** | 0.0104 | 0.0037 | 8 |
| step wall (SPLIT=1) | 9807.9 | 70.4 | 24.9 | 8 |
| step busy_sum (SPLIT=1) | 8557.0 | 14.0 | 5.0 | 8 |

Per-run µs/step: 186.6, 186.6, 186.9, 186.3, 185.8, 185.0, and the two
remaining `A0` logs. Aggregated `ceiling.json` (which drops the first run,
n=7) independently reports `ref_us = 186.214`, `share_pct = 2.1755`.

**Atlas resolution on this exact row:** `ceiling.json` records this kernel as
`touched: false` with an untouched-neighbour delta of `0.329 ± 0.655 µs/step`.
So the atlas's own resolution here is ±0.655 µs/step and the row sits ~285σ
above it. The "below the atlas's resolution" escape hatch does not apply.

## 3. Geometry — independent confirmation of the 1-TG / 39-call column

From `research/artifacts/fern-r105d/decode-dispatch-census.csv`, family
`prefill_router_tournament_ordinal_norm_active64_v2_bfloat16_t_float_uint32_t_float`,
captured independently of the atlas:

| field | value |
|---|---|
| grid_threads | 256 |
| threads_per_tg | 256 |
| **threadgroups** | **1** |
| simdgroups_per_tg | 8 |
| **calls_per_step** | **39** |
| tg_per_core_C20 | 0.05 |
| occupancy class | **`SINGLE_TG`** |
| layer ordinals | 16, 26, 36, … 386, 396 |

This matches the advisor's static read (`rows: 1` hard-coded at `:9732`; grid
`(256, rows, 1)` / threadGroup `(256,1,1)` at `:10307-10312`; MLX `grid` is
total threads so TGs = 256/256 = 1) and the 39 calls/step seen in the atlas.

**19 of 20 cores are dark for the whole 4.775 µs of every one of the 39 calls.**
That is the entire content of the opportunity.

## 4. % of DRAM peak

Buffer shapes from `research/artifacts/fern-r106g/dispatch_raw.tsv`. That
capture is *prefill* (grid `256x512x1`, rows=512), so the per-row buffers are
divided by 512 to get the decode (rows=1) footprint; the score table is not
per-row and is read whole on every call.

| buf | prefill shape | prefill B | decode B/call |
|---|---|---|---|
| 0 in | `bfloat16[1,512,256]` | 262 144 | 512 |
| 1 in | `float32[256]` score table | 1 024 | **1 024** |
| 2 out | `uint32[1,512,8]` | 16 384 | 32 |
| 3 out | `float32[1,512,8]` | 16 384 | 32 |
| **total** | | | **1 600 B** |

- **62 400 B/step** (39 × 1 600).
- At 186.263 µs/step that is **0.335 GB/s = 0.123 % of the 273.0 GB/s M4 Pro
  peak** the atlas denominates in
  (`research/maple-alphonse-r109e-bwatlas.py:38`).
- SPLIT-deflated (§5) it is **0.507 GB/s = 0.186 %**.

**Call it 0.1–0.2 % of DRAM peak.** For scale, the atlas's bytes-regime
families run 84–98 % of peak; this kernel is ~700× below them. Two thirds of
its 1 600 B is a 1 KB constant score table that is certainly cache-resident
across 39 calls, so true DRAM traffic is lower still.

**This is a pure latency kernel with no byte side whatsoever.** Nothing about it
is purchasable by reducing bytes; the only thing to buy is the idle-core time.

## 5. Raw vs deflated (reported raw, as instructed)

All figures above are **raw SPLIT=1**, per the instruction that the advisor
applies the haircut. For his convenience the deflation is:

- Banked per-CB constants: 1.554 µs/CB (mine) and 1.681 µs/CB
  (`research/tanjiro-r87a-prereg.md:190`).
- 39 calls × (1.554 … 1.681) = **60.6 … 65.6 µs/step** of pure SPLIT=1 overhead.
- Deflated guest = **120.6 … 125.6 µs/step**, midpoint **≈123 µs/step**
  (3.09–3.22 µs/call).

Consistency check: SPLIT=1 step wall 9807.9 µs vs the SPLIT=0 steady step
~8218 µs measured on this host in R116-A ⇒ **+19.3 %**, matching the banked
`+19.6 %` SPLIT=1 wall inflation. The regime is behaving as documented.

## 6. Pricing the last lever (`L-THIRD-CELL-NEEDS-CALL-COUNT`)

The advisor's bracket was "~48 µs/step (dispatch-removal floor) or ~77 µs/step
(gate_sp's realized 29.4 % applied to a guest as big as gate_sp's 261.6)".

**The guest is not as big as gate_sp.** 186.263 / 261.6 = **71.2 %**. So the
gate_sp-scaled price is 0.712 × 76.8 = **54.7 µs/step**, which lands *between*
the two brackets.

| pricing model | rate | × 39 calls | score at alphonse's realized rate |
|---|---|---|---|
| dispatch tax (0.4478 µs) | floor-of-floor | 17.5 µs/step | +0.10 % |
| Rule 57 symmetric (1.2375 µs) | | **48.3 µs/step** | +0.28 % |
| **gate_sp realized 29.4 % × 186.3 (same SPLIT=1 regime)** | | **54.8 µs/step** | **+0.32 %** |
| alphonse's measured 1.920 µs/dispatch | | 74.9 µs/step | +0.44 % |
| gate_sp realized 29.4 % × 123 (SPLIT-deflated) | | 36.2 µs/step | +0.21 % |

Score column uses the campaign's only *realized* anchor rather than a model:
alphonse's merged #700 turned −76.8 µs/step into **+0.45 % score**, i.e.
**0.00586 % score per µs/step**, on this host and this class.

**Verdict for the go/no-go:**

- Central estimate **≈55 µs/step ⇒ ≈+0.32 % score**.
- That is **below Rule 105.12's 60 µs/step slot floor**, by ~9 %.
- It clears the +0.25 % ship threshold by only **1.28×**.
- If the haircut is applied before the slot test, it falls to ~36 µs/step /
  +0.21 % and **fails the ship threshold outright**.

So the honest read is: **the last lever is real, but it is materially smaller
than gate_sp was, and it sits on the wrong side of the slot floor on the
central estimate.** It is a marginal buy, not a repeat of #700.

## 7. Two structural notes for alphonse's arm

**(a) The guest fits inside the host's per-call duration — favourable.**
Proposed host `shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` (`:7347`) runs
285.5 µs/step over the **same 39 calls/step** = 7.32 µs/call, versus the guest's
4.775 µs/call. Same call count and guest is 65 % of host duration, so the
pairing is structurally clean — no call-count mismatch to reconcile, unlike a
30-call host.

**(b) The threadgroup rewrite carries a bit-exactness risk that should be
cleared first.** The host is 256 TGs of **64** threads; the guest is 1 TG of
**256** threads = 8 simdgroups. Rewriting the guest to 64 threads takes the
tournament reduction over 256 experts from 8 simdgroups to 2, which **changes
the shape of the reduction tree**. This kernel produces a top-8 **argmax over
256 experts**. A reordered tournament can break a near-tie differently, and a
different expert set is not a rounding difference — it changes the output
token. AGENTS.md already warns that a near-tie argmax may resolve differently
across Apple Silicon generations, and the public fixtures were generated on M5.

Recommendation: before spending Metal time, verify that the rewritten reduction
preserves the *exact* comparison order and tie-break of the current tournament
(or prove no ties occur in the 512-token teacher-forced window). This is a
cheap static check that protects a hard correctness gate — every checked greedy
token must match, and a mismatch publishes no score at all.

Also note the atlas base predates #700: these logs show `dispatches=406.0`,
whereas alphonse's merged arm is at 366. The router row itself is untouched by
#700 (it is not in the QKV grid), so 186.263 µs/step carries over, but the
*denominator* for any "% of decode wall" restatement should be the post-#700
wall, not 8557.

## 8. Provenance index

| claim | file |
|---|---|
| 186.263 µs/step, 4.775 µs/call, 2.1775 % | `research/r87a-runs/ceiling/p*-A0.log` (n=8), `research/r87a-runs/ceiling.json` |
| SPLIT=1 regime | `research/tanjiro-r87a-campaign.sh:64`; `cbs==dispatches==406` in every log |
| noise floor ±0.655 µs/step, `touched:false` | `research/r87a-runs/ceiling.json` |
| 1 TG / 256 threads / 8 simdgroups / 39 calls | `research/artifacts/fern-r105d/decode-dispatch-census.csv` |
| buffer sizes | `research/artifacts/fern-r106g/dispatch_raw.tsv` |
| 273.0 GB/s denominator | `research/maple-alphonse-r109e-bwatlas.py:38` |
| 1.681 µs/CB SPLIT=1 overhead | `research/tanjiro-r87a-prereg.md:190` |
| host kernel 285.5 µs/step, 39 calls | same `A0` logs |

## 9. Correction to the requested inventory row

The advisor asked for a second pair of eyes on
**`DARKBLOOM_DECODE_QKV_GATE_FUSED` read as `!= "0"` at
`LagunaRuntimeModel.swift:5078`**.

**That symbol does not exist anywhere in `Sources/` at my branch base.**
`grep -rn "DECODE_QKV_GATE_FUSED" Sources/` and `grep -rn "GATE_FUSED\|QKV_GATE"
Sources/` both return nothing, and `LagunaRuntimeModel.swift:5078` at my base is
inside a threadgroup-normalize MSL string, not an env read.

Explanation: my branch base is `93688bfa` (merge of #693, edward). Alphonse's
#700 merged later, at advisor HEAD `206cf037`, which is not an object in my
checkout. `DARKBLOOM_DECODE_QKV_GATE_FUSED` is the env switch **introduced by
#700** — consistent with the description of that arm as "one binary
env-switched".

So I can confirm the useful half: **the flag is not pre-existing and was not
missed by the R116-A census.** The census covered every default-OFF decode flag
present at `93688bfa`, and this one did not exist then. Confirming the `!= "0"`
default-ON reading requires a checkout containing #700, which I do not have; it
should be re-checked by someone based on `206cf037` or later.
