# r98-D: dispatch geometry and M4 measurements, recorded under HOLD

Written in response to the advisor HOLD on PR #543
([comment 5231843366](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/543#issuecomment-5231843366),
2026-08-09T13:46:53Z), which asked that any occupancy numbers and any M4
measurements taken against the old base be committed to a `research/*.md` file
before work stops.

**Base these numbers belong to:** `450953e5c8287bfa1f409addf568d7851458cf94`,
i.e. `e510bb3d` plus one research-only document (zero submitted bytes; the
advisor previously confirmed that move scientifically inert). **They do not
transfer to `4f3108c4`.** `LagunaRuntimeLayers.swift` no longer exists on the
new base and `LagunaRuntimeModel.swift` was rewritten by ±9716 and then +2928
lines, so every line anchor and every kernel-identity claim below must be
re-derived before reuse.

**Host for all timing:** Apple M4 Pro, **20 GPU cores**, 48 GiB unified memory,
macOS 26.5.2, Metal 4. Reports Apple GPU generation 16, therefore never selects
the `_nax` prefill kernels used by the ranked M5.

## 1. Dispatch geometry (the advisor's standing request)

Extracted from the dispatch call sites, not inferred. Threads/threadgroup is the
`threadGroup:` argument; threadgroup count is `grid.x / threadGroup.x`.
Simdgroups per threadgroup assumes 32-wide simds.

| kernel | grid.x | threads/TG | **TG count** | simds/TG | total threads | TGs per GPU core (20) |
|---|---|---|---|---|---|---|
| **routed gate/up R1** `..._packed_top8keys_r1_bf16_v2` (**my site**, shipped default) | `8*256*64` = 131072 | 64 | **2048** | 2 | 131072 | 102.4 |
| routed gate/up R0 arm `..._packed_top8keys_bf16` (not selected) | `8*128*64` = 65536 | 64 | **1024** | 2 | 65536 | 51.2 |
| shared gate/up rows1 `lagunaSharedSwiGLUQMVRows1Kernel` (tiles = 256) | `256*64` = 16384 | 64 | **256** | 2 | 16384 | 12.8 |
| shared gate/up non-rows1 fallback (tiles = 128) | `128*64` = 8192 | 64 | **128** | 2 | 8192 | 6.4 |
| down+residual `..._sh_stage4_v6` (generated, shipped default) | `(2048/4)*288` = 147456 | 288 | **512** | 9 | 147456 | 25.6 |
| `lagunaRoutedDownReduceKernel` (never-taken fallback) | `(2048/4)*256` = 131072 | 256 | **512** | 8 | 131072 | 25.6 |

Constants used: `hiddenSize = 2048`, `moeIntermediateSize = 512`,
`numExperts = 256`, `numExpertsPerTok = 8`.

### 1.1 The rung I actually ran does **not** trade TLP for ILP

This is the specific confound the advisor flagged, and it does not apply to this
rung. My change is entirely inside the kernel body: it replaces a depth-1
software pipeline with full 4-block staging, raising codes in flight per lane
from 16 B to 64 B and scale bytes from 2 to 8.

`git diff 450953e5 HEAD -- Sources/` contains **no `grid:` or `threadGroup:`
hunk at all** (verified: the grep over the diff is empty). Both legs dispatch
**2048 threadgroups × 64 threads**. So for this rung:

- ILP / memory-level parallelism: **raised** (4x outstanding weight bytes/lane)
- threadgroup count: **unchanged** (2048)
- threads per threadgroup: **unchanged** (64)
- dispatch count: **unchanged** (no kernel added or removed)
- bytes moved, arithmetic, accumulation order, `simd_sum` tail: **unchanged**

A negative result on this rung is therefore attributable to ILP alone, or to
register pressure from the staging arrays — not to lost occupancy. That is a
different situation from the "more rows per simdgroup" rungs, which raise ILP
while dividing the threadgroup count, and which do need the table above to be
interpretable.

### 1.2 Occupancy caveat that the table does not capture

Threadgroup count is only half of occupancy; the other half is how many
threadgroups are resident per core, which is bounded by register and
threadgroup-memory use per thread. My change raises per-lane register demand
(4x staged codes plus 4x scale bytes) at fixed threadgroup geometry, so if it
ever regresses, the mechanism to check first is reduced residency from register
pressure, not reduced threadgroup count. The prepared fallback is a depth-2
(32 B) variant. I have no on-device register-count readout for these kernels, so
this remains an inference, not a measurement.

## 2. M4 measurements against the old base (all of them)

### 2.1 Bracketed decode/prefill timing, `./benchmark.sh --local-iterate`

```
leg      wall      commit    decode s/tok        prefill s/tok
base A   13:21:12  61c8763   0.0130002975234375  0.00113808170703125
cand     13:31:20  0ff6d26   0.0129596627578125  0.001121568765625
base B   13:39:40  a78c43c   0.0129504069062500  0.001112815509765625   (base kernel restored)

cand - mean(base)  = -15.7 us/token  (-0.121 %)
base B - base A    = -49.9 us/token  (-0.384 %)   <- identical code in both legs
prefill B - A      = -2.22 %                      <- must be exactly 0 by construction
```

Artifacts: `research/artifacts/fern-r98d-base-A.json`,
`fern-r98d-rung1-cand.json`, `fern-r98d-control-B.json`; reducer
`research/fern-r98d-compare.py`.

**Reading: no timing signal.** The identical-code control spread is three times
the candidate's nominal effect, and both axes drift monotonically downward with
wall-clock across all three legs, including a prefill drift that is impossible
by construction. My preregistered 15 µs/step advance bar was set below this
host's own drift. The candidate nominally cleared it; I do not claim it. The M4
screen has no resolving power for this effect and is only a bit-exactness and
gross-regression gate.

### 2.2 Correctness, candidate, `./benchmark.sh --local-submit`

Artifact `research/artifacts/fern-r98d-rung1-localsubmit.json`, commit `30dbb4c`,
`timestamp 2026-08-09T13:44:12Z`, `passed = true`.

```
passed_correctness   true      max_abs_diff  0        checked_steps 1025
error                ""        first_failing_case/step/layer  null / null / null
decode_seconds_per_token   0.008946454056695993
prefill_seconds_per_token  0.00111165966796875
golden_hash f49e4c2c...   weights_hash aff99430...
```

The `decode_speedup` (1.549) and `prefill_speedup` (0.331) fields in that file
divide by **pinned M5 calibration constants**, not a same-session M4 baseline, so
they carry no candidate-specific information here; the unchanged base reproduces
the same `passed_prefill_speedup_floor = false`.

### 2.3 Upstream-equivalence oracle

`research/artifacts/fern-r98d-rung1-oracle.log` and
`fern-r98d-control-oracle.log`: candidate and unchanged base are
**byte-identical** — same prefill logits (max abs error 0.125, mean
0.011933609), same argmax (5991 == 5991), all 8 teacher-forced decode steps
differing by exactly 0.0, `EQUIVALENCE_EXACT_STEPS=8`, same exit status. The
residual prefill delta is the pre-existing generation-16 divergence on this host;
the candidate contributes zero to it.

## 3. Findings from the old tree that may or may not survive the base swap

Recorded so the audit does not have to redo them, each flagged with how much of
it is likely to transfer.

1. **The brief's nominated "site 1" was dead code.**
   `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_wide_bf16_v1` requires
   `DARKBLOOM_QMV_WIDE_CODES=1`, which defaults OFF, and
   `RESEARCH_ARCHIVE_through-round-91.md:267` records that variant as **not
   bit-exact**. *Likely to transfer* if the flag and archive entry survive; worth
   re-checking the flag default on `4f3108c4` before any brief re-nominates it.
2. **The live shared gate/up kernel is the most latency-exposed but not worth
   attacking.** Genuinely depth-0 (4 serial K iterations, pointer-form `qdot`),
   but 237.6 µs/step isolated, exposure ≈ 0.10, so a 30 % win is worth ~0.107 %
   of score — under the noise I can defend. *The exposure number is measured on
   the old tree and must be re-measured.*
3. **The down/residual family had no staging headroom.** The shipped default is
   the *generated* `..._sh_stage4_v6`, already fully staged with no K loop,
   812.8 µs/step at 89.3 % of this host's roofline. `down_reduce` is a
   never-taken fallback and the literal `stage4_v6` source only runs when the
   halved plane is absent. *Most at risk from the swap* — this is exactly the
   family the advisor says was rewritten.
4. **The routed gate/up R1 kernel was the only high-exposure member still on a
   shallow pipeline:** 1497.3 µs/step, exposure ≈ 1.0, 248.3 GB/s = 91.0 % of
   this host's roofline. That roofline fraction is *this host's*; the ranked part
   needs roughly 191 kB in flight to saturate against roughly 80 kB here, which
   is the whole reason a kernel can look bandwidth-bound here and be
   latency-starved there.
5. **`mergedSharedActivated` in the old `LagunaRuntimeLayers.swift` was declared
   and never assigned** — a dead hook, not a live fusion. Moot if that file is
   gone.

## 4. Status and what I did not do

- The advisor HOLD arrived while I was preparing the official submission. I
  **have not submitted and will not**. One `mlxfast submit --model "senpai"`
  invocation had already been dispatched and **failed local client-side
  validation in 0.6 s** with `submission note must be at least 5 KiB (3204 bytes
  provided)` — a note-length check that runs before any network call, so **no
  submission was created and no receipt was spent**. Receipt budget remains
  **6 of 6**. I did not retry. Verified against the server rather than assumed:
  `mlxfast submissions` returns 141 rows, none of which carry any commit from
  this branch (`0ff6d26`, `30dbb4c`, `976654f`, `ec3b72d` all absent; grep count
  0). The failure was purely client-side.
- No further GPU spend on this tree. Nothing was mid-flight when the HOLD
  landed, so nothing had to be left to drain.
- **I have not rebased**, per the explicit instruction. The branch still sits on
  `450953e5`.
- `research/fern-r98d-submission-note.md` is retained as a drafting artifact
  only and is marked at the top as never submitted.
- Byte budget on the old base was `current=2899396/3000000 headroom=100604
  growth=-80/262144 files=141`. My change *reduces* the surface by 80 bytes, so
  it stays feasible under the collapsed `headroom = 16151` on `4f3108c4` — but
  only the kernel-body rewrite is; any *additional* wider-load variants are now
  byte-constrained first, as the advisor notes.

Awaiting the rewritten brief bound to `4f3108c4`, or a close.
