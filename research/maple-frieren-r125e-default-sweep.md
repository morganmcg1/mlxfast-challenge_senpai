# R125-E: shipped-default env-knob sweep on the live composition

Student maple-frieren, PR #733, base `a9de9e8f21188715f6d80ada4b581bcd50d4ec81`.
Host: Apple M4 Pro, 14 CPU, 48 GiB, macOS 26.5.2, Apple GPU generation 16
(never selects `_nax`). All timing below is **decode steady-step on this M4
Pro**; local prefill is not interpretable and is not reported.

## Instrument

`research/frieren_r125e_arms.sh` + `research/decode_probe.py`: one worker process
per arm (every `DARKBLOOM_*` knob is a file-scope Swift `let`, parsed once per
process, so in-process A/B is impossible), golden
`public_longcopy_gate_english_512_256`, 512-token seed, 224 teacher-forced
one-token steps, `DARKBLOOM_STARTUP_MEMORY_PROFILE=full` (ranked 200/200/50
atlas profile, **not** the 48 GiB host default). Statistic per run = median
steady step; step 0 dropped (one-time KV concat). Every run reports its
teacher-forced divergence count; **every run in this report had 0 divergences**.

Drift handling: each arm run is differenced against the control level linearly
interpolated between the nearest earlier and later `C` run of the same pass
(`research/frieren_r125e_analyze.py`). Pricing: 1 µs/step = 0.00586 % score;
ranking bar 25.6 µs/step = 0.378 %. Since every knob here is decode-only,
prefill_speedup = 1 exactly and `ns = decode_speedup^0.75`, which is what the
% score column reports.

Cost per arm ≈ 55 s (≈41 s load + steps), versus 150-210 s per `--local-iterate`
arm at σ = 33.6 %.

## 1. `DARKBLOOM_SHARED_ROUTED_QMV_FUSED` — CONFIRMED LOSS (advisor's decision input)

n = 6 per arm, interleaved `C C F F C C F F C C F F C`, single session,
profile=full, 224 steps, 0 divergences everywhere.

| | median steady step (ms) |
|---|---|
| control (shipped default, FUSED=0) | 8.239, 8.180, 8.088, 8.217, 8.216, 8.223 → mean 8.1938 |
| FUSED=1 | 8.204, 8.236, 8.218, 8.279, 8.301, 8.256 → mean 8.2490 |

Drift-corrected paired deltas (µs/step): −15.3, +36.3, +87.0, +105.0, +82.7, +35.3.

- **point +55.2 µs/step slower**
- 95 % paired bootstrap CI **[+18.9, +85.9] µs/step**
- Bonferroni k=3 (98.3 %) CI **[+10.3, +91.6] µs/step** — excludes 0 even after
  the multiplicity correction
- score **−0.323 %**, 95 % CI [−0.504, −0.111]
- control run-to-run sd 55.3 µs/step ⇒ achieved detection floor at n=6
  2·sd/√n = **45.2 µs/step = 0.265 % score**. The measured loss is above that
  floor; a *win* of this size would also have been resolvable.

**Verdict: the fused shared+routed grid-append QMV is a real ~0.3 % loss on this
host at n=6.** It is not a candidate, and it therefore does not compete with
maple-alphonse's TG=256 landing (#729, +0.38 %). Recommendation: take TG=256 and
leave `DARKBLOOM_SHARED_ROUTED_QMV_FUSED` at its shipped default 0.

Caveats stated honestly: (a) M4 Pro, gen 16 — but the fused path contains **no
architecture or `_nax` predicate** anywhere in its guard chain (see §2), so the
same dispatch-count change happens on M5; what could differ across generations
is the *sign of the scheduling trade-off*, not reachability. (b) The fused kernel
saves one encode per MoE layer per step but serializes 256 shared tiles into the
same grid as the routed tiles; on this host that scheduling cost exceeds the
encode saving.

W&B: `6r8i5rcg` — https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/6r8i5rcg

## 2. Reachability audit (why several briefed knobs cannot be timing experiments)

Static audit of every knob's guard chain and dispatch site (`Sources/MLXFastModel/LagunaRuntimeModel.swift`
unless noted):

| knob | default | reads | reachable on the **default scored path**? | bit-identical? |
|---|---|---|---|---|
| `SHARED_ROUTED_QMV_FUSED` | 0 | 8177 | **yes** — full chain 11462/11417/11038/11062/11071/11076/11084, all co-guards default-on, no gen predicate | yes |
| `NORM_AFFINE_QKV_PF` | 4 | 5342 | **no** — the `laguna_norm_affine_qkv_qmv_i8g32_*` family (dispatch 5638/5653) needs affine i8/g32 QKV; the shipped path prepares NVFP4 g16 (3048, 5803) and decodes via `lagunaDecodeNVFP4QKVGate/R1` (6078) | yes (inert) |
| `NORM_AFFINE_QKV_STAGE` | off | 5322 | **no** — same dead family; also forces `pf=0` (5542) | yes (inert) |
| `L5_UNROLL` | 2 | 3813 | **no** — call site 6583 sits after the default-taken native-affine NVFP4 o_proj branch, which always returns at 6514/6530 | yes (inert) |
| `ROUTER_WEIGHT_PREFETCH` | 1 | 696 | **ACTIVE** (audit below) | yes |
| `NVFP4_NIBBLE_SPLIT` | 1 | 6787 | **yes** — header at 6915 feeds 17 decode QMV/down dispatches; widest blast radius | yes |
| `DECODE_ASYNC_STAGE` | `at:0,1,7,15,23,31,39` | 744 | **yes** — `decodeFireMask` 11689/11722 → `asyncEval` 11939/11951; submission boundaries only | yes |
| `OPROJ_ROWS_PER_SIMDGROUP` | 2 | `LagunaOProjGeometry.swift:53` | **yes** — dispatch 4641/4656 on the default-live gated-affine NVFP4 o_proj | yes |
| `OPROJ_SIMDGROUPS` | 2 | `LagunaOProjGeometry.swift:93` | **yes** — same dispatch | yes |
| `GRID_APPEND` | — | — | **the knob does not exist**: no `DARKBLOOM_GRID_APPEND` read anywhere in the tree. The brief's item 8 is a mis-naming of the fused grid-append knob, i.e. item 1. | n/a |

No screened knob gates route-sort, expert-index/carrier construction, pairwise
scale, gather geometry, declined-shape warmup, or gather-QMM bounds, so none of
them touches the promoted `_nax` mechanism (advisor item 6). The only `_nax`
gate in the model sources, `lagunaNAXAvailable` (242-247) via
`lagunaExpertAlignedGatherEnabled` (253-265), is used at 10807/10982/10995 —
all **prefill** sorted-gather sites, none on the decode MoE gate/up.

Two extra knobs were added to the screen under the brief's rule (code that reads
them plus a mechanism): `OPROJ_ROWS_PER_SIMDGROUP` and `OPROJ_SIMDGROUPS`, both
reachable on the default decode o_proj and both bit-identical.

Consequence for the run budget: three briefed knobs (`NORM_AFFINE_QKV_PF`,
`NORM_AFFINE_QKV_STAGE`, `L5_UNROLL`, i.e. 9 of the 22 planned arms) are
**structurally inert** on the shipped path — a knob on an unused fallback is not
a timing experiment. They are screened last and at reduced n, with the
prediction "delta indistinguishable from 0" recorded here in advance.

## `ROUTER_WEIGHT_PREFETCH` reachability, settled by reading the dispatch

My first table stated both "reachable" and "inert unless rowsPerThread==1"
without resolving which side the shipped configuration lands on. Resolved by
static read, not timing — verdict **ACTIVE**, three separately compiled kernels:

- Guard: `lagunaRouterPrefetchGroups(rowsPerThread:prefetch:)` at
  `LagunaRuntimeModel.swift:876-879` returns `0` unless `rowsPerThread == 1`.
- At `:929-931`, `simdGroups = 512/32 = 16` and
  `rowsPerThread = rowsPerGroup >= simdGroups ? rowsPerGroup/simdGroups : 1`.
  Shipped `rowsPerGroup = 8` (`:676-682`) ⇒ `8 >= 16` is false ⇒
  `rowsPerThread = 1`, so the guard **passes**. Prefetch is inert only at
  `rowsPerGroup` 32/64; live at 1, 2, 4, 8, 16.
- `prefetchGroups` = 0 / 1 / 1 for prefetch 0 / 1 / 5, and the emitted kernel
  name differs per level (`:1127`, suffix `""` / `_pf1` / `_pf1c`), so the table
  built at `:1119-1148` (21 pairs, key `rowsPerGroup*8 + prefetch`; shipped key
  `65`) holds three distinct MSL texts.
- Level 0 vs 1 differs by a hoisted 4-register load block (`:937-950`) plus a
  rewritten accumulator (`:971-1001` vs `:1003-1023`). Level 1 vs 5 is the same
  block moved from before the norm reduction (`:1082`) to after the
  `threadgroup_barrier` (`:1095`) — pure load scheduling.
- Enclosing decode branch is default-taken: `:11417-11423` requires
  `x.dims(1,1,2048)` (the one-token decode shape) and the flag defaults on at
  `:579-580`. Launch geometry is prefetch-independent (`:1226-1227`,
  `grid = tiles*512`, `threadGroup = 512`), and the prefetch loads use the same
  addresses in the same ascending order, so numerics are bit-exact.
- Independent corroboration: `research/maple-tanjiro-r103b-kernel-text-differential.md:645`
  records `DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0` reproducing the pre-prefetch
  kernel byte-identically at the shipped geometry.


## Kernel-level reachability trace: attempted, no usable output

`research/frieren_r125e_trace.sh` ran arms C and FUS with
`DARKBLOOM_GPU_PROFILE=1` and `decode_probe.py --profile --profile-top 80`
(10:47-10:49Z). Both arms completed (rc=0, 0 divergences) but the probe reported
`profile: no GPUPROF records (was DARKBLOOM_GPU_PROFILE=1 set?)`, i.e. the
worker exposes no per-kernel record under this env name in the current tree.
The reachability conclusions above therefore rest on the static call-graph audit
plus the behavioural facts that are available: the FUSED arm moves timing (so
its chain is live) and the inert arms are predicted not to (screened below).
Worker stderr does confirm the shipped composition on this host:
`narrow-scales lane-major pairwise: qkv/oproj`, `packed-scales active: shared
gate/up halved`, `shared down halved`, `packed routed gate/up bank prepared`,
`lm_head prune active`, `routed swiglu qmv packed dispatch`.

## Default-flip anchors (for whichever arm wins)

| knob | file:line of the default | current | flip form |
|---|---|---|---|
| `ROUTER_WEIGHT_PREFETCH` | `Sources/MLXFastModel/LagunaRuntimeModel.swift:696-703` | `return 1` | `return 0` or `return 5` |
| `DECODE_ASYNC_STAGE` | `Sources/MLXFastModel/LagunaRuntimeModel.swift:744-747` | `?? "at:0,1,7,15,23,31,39"` | replace the literal |
| `NVFP4_NIBBLE_SPLIT` | `Sources/MLXFastModel/LagunaRuntimeModel.swift:6787-6792` | `else { return 1 }` | `return 0` or `return 2` |
| `OPROJ_ROWS_PER_SIMDGROUP` | `Sources/MLXFastModel/LagunaOProjGeometry.swift:53-62` | `return 2` | `return 1` / `return 4` |
| `OPROJ_SIMDGROUPS` | `Sources/MLXFastModel/LagunaOProjGeometry.swift:93-102` | `return 2` | `return 4` |

Each flip is a one-token edit inside an existing `else` branch on an already
editable file, so the portable hunk for a winner is 1 line and the env override
stays available for the reverse probe.

### Rebase check against the Maple advisor head `18ac6015`

The advisor asked that any winner be expressed as a compiled-default hunk on
`18ac6015c6c2c52ae2fa8830b23d249b35b6f448`, anchored by symbol plus line. I
verified that head directly:

- `let lagunaRouterWeightPrefetch: Int = {` is at `18ac6015`
  `Sources/MLXFastModel/LagunaRuntimeModel.swift:704`, and the `else { return 1 }`
  default is at **:709**. The 9-line block is byte-identical to my base, so the
  flip is `return 1` → `return 0` at that line, no conflict.
- The only `LagunaRuntimeModel.swift` delta between my base
  `a9de9e8f` and `18ac6015` is the prefill-only `DARKBLOOM_EXPERT_BOUNDS_SIDECAR`
  / `lagunaFusedSortedRoutedGateUp` N1 work (+27/-6 lines) plus receipt comments.
  It does not touch the router-prefetch guard, the router kernel table, or any
  decode branch, so the decode measurement transfers.

Note the two o_proj geometry knobs carry
a prior from nezuko R117-C recorded in the doc comment at
`LagunaOProjGeometry.swift:45-52`: `rps=1` measured *worse* on a 20-core M4
(-54.7 vs -83.8 us) but is the M5-relevant point because it reproduces the same
~51 simdgroups/core ratio on 40 cores. My screen re-measures all three on the
**current** composition; a local `rps=1` loss is expected and is not by itself
evidence against the M5 case.

## 3. Screen: 32 scored runs, counterbalanced, drift-corrected

One job, 33 runs (run 0 unscored warm-up), `STEPS=224`, `PROFILE=full`, arm
order `C RP0 RP5 NS0 NS2 C ASOFF ASDEN ASSPA ASLAD C ASNRM OPR1 OPR4 OPSG4 C`
followed by its exact reverse, so every arm is measured once early and once
late and each is bracketed by controls. Δ is against the linear interpolation of
its two neighbouring controls; **n=2 per arm, so no line here is a confirmed
effect** — the screen is a ranking device only (pre-registered). 0 divergences
in all 33 runs. Control median drifted 8.158 → 8.318 ms across the job, which is
exactly why interpolation rather than a pooled control mean is used.

| arm | env level | Δ µs/step | per-pass Δ | % score | read |
|---|---|---|---|---|---|
| `OPR1` | `OPROJ_ROWS_PER_SIMDGROUP=1` | **−64.2** | −88.4, −40.0 | +0.376 | closed axis, replication only |
| `RP0` | `ROUTER_WEIGHT_PREFETCH=0` | **−55.3** | −45.6, −65.0 | +0.324 | leader, both passes negative → confirm |
| `OPSG4` | `OPROJ_SIMDGROUPS=4` | −40.9 | −74.8, −7.0 | +0.240 | inconsistent, closed axis |
| `ASSPA` | `DECODE_ASYNC_STAGE=at:0,1,15,31` | −33.0 | −3.4, −62.6 | +0.193 | best async arm → confirm |
| `ASDEN` | `=at:0,1,3,7,…,39` | −12.0 | +16.4, −40.4 | +0.070 | noise |
| `C` | shipped defaults | 0 (7 runs) | — | — | reference |
| `OPR4` | `OPROJ_ROWS_PER_SIMDGROUP=4` | +1.7 | +18.4, −15.0 | −0.010 | noise |
| `NS2` | `NVFP4_NIBBLE_SPLIT=2` | +25.3 | +18.6, +32.0 | −0.148 | better of the two NS levels → confirm |
| `RP5` | `ROUTER_WEIGHT_PREFETCH=5` | +25.4 | +37.8, +13.0 | −0.149 | late-placement prefetch is worse |
| `NS0` | `NVFP4_NIBBLE_SPLIT=0` | +55.6 | +71.2, +40.0 | −0.326 | consistent loser |
| `ASLAD` | `=ladder8` | +193.0 | +224.8, +161.2 | −1.131 | consistent loser |
| `ASOFF` | `=off` | +1140.5 | +1162.2, +1118.8 | −6.683 | async staging is load-bearing |
| `ASNRM` | `=norm` | +1158.9 | +1304.8, +1013.0 | −6.791 | consistent catastrophic loser |

Three results are already decided by the screen alone, because the effects are
20-40× the per-arm noise and both passes agree:

- **`DECODE_ASYNC_STAGE` off (`ASOFF`, +1.14 ms/step) and `norm`
  (`ASNRM`, +1.16 ms/step) are catastrophic.** The shipped
  `at:0,1,7,15,23,31,39` submission-boundary schedule is load-bearing, worth
  ~14% of decode step time on this host. `ladder8` (+193 µs) also loses clearly.
  Only the two hand-picked variants near the shipped schedule
  (`at:0,1,15,31` and the dense list) are in the noise band. There is no cheap
  win hiding on this axis; the shipped default is at or near a sharp optimum.
- **`NVFP4_NIBBLE_SPLIT` is at its best shipped value.** Both alternatives are
  *worse* in both passes (level 0: +71/+40 µs, level 2: +19/+32 µs). This is the
  advisor's most-wanted number and the screen answer is "the default 1 wins".
  Confirmed at n=6 below anyway, per the addendum, because the advisor asked for
  the number rather than the ranking.
- **`ROUTER_WEIGHT_PREFETCH=5` (late placement) loses**; only level 0
  (prefetch removed) ranks ahead of the default.

`OPR1` ranks first but the advisor closed that axis in #718/#719 after this job
was launched; both `OPR` arms and `OPSG4` are reported as free replication and
were never eligible for a confirm slot. Note `OPR1`'s per-pass spread
(−88 vs −40 µs) is larger than its mean, and the R117-C prior says `rps=1` is
*worse* on 20-core M4 — so this local n=2 lead should not be read as evidence
against the promoted `rps=2`.

## Which QKV decode kernel actually runs (settles a contradicting review)

A frontier review of this branch concluded that the shipped decode QKV path is
`lagunaNormAffineQKV` (affine INT8 g32) and that the NVFP4 QKV kernels are dead.
That is **backwards** on this composition, and the deciding line is a default:

- `LagunaRuntimeModel.swift:3048-3055`: `lagunaNativeAffineNVFP4From` is enabled
  unless `DARKBLOOM_NATIVE_AFFINE_NVFP4 == "0"`, and its layer threshold
  `DARKBLOOM_NATIVE_AFFINE_NVFP4_FROM` defaults to **`"0"`**.
- `:3100-3116`: with `from = 0`, `(layer ?? 0) >= from` holds for **all 40
  layers**, so `lagunaNativeAffineWeight` returns `groupSize 16, bits 4,
  mode .nvfp4` for wq/wk/wv every time. The affine INT8 g32 return at
  `:3117-3125` is never reached on the default path.
- Consequences inside `prepareNativeAffineQKVWeight` (`:5803-5885`):
  `foldGateIntoBank` requires `q.groupSize == 32 && q.bits == 8 && q.mode ==
  .affine` (`:5828-5829`) ⇒ false ⇒ `_nativeAffineGProj = gate` and
  `_nativeAffineQKVGateRows` stays `0 != nHeads`. The nvfp4-only lane-major
  scale bank at `:5871-5883` is taken instead, which is exactly the
  `narrow-scales lane-major pairwise: qkv/oproj` line the worker prints.
- Therefore at the decode guard `:6042-6049` the clause
  `fusedAffine.mode == .affine, bits == 8, groupSize == 32` is **false**, so
  `fusedQKV == nil`, and `:6068-6078` takes `lagunaDecodeNVFP4QKVGate`
  (`_nativeAffineQKVGateRows != nHeads` plus the NVFP4 o_proj clauses), with
  `lagunaDecodeNVFP4QKVR1` as its fallback (`:6079-6084`).

So my original inertness verdict stands: `NORM_AFFINE_QKV_PF` and
`NORM_AFFINE_QKV_STAGE` gate a kernel family that no layer selects. Two
corrections for whoever picks up the review's list:

- its proposed "hardcoded rows/8 per TG in `lagunaNormAffineQKV` (`:5638-5657`)"
  geometry experiment is on that same dead family and is **not** a timing
  experiment as written;
- its exclusion of `DECODE_NVFP4_QKV_R1` (`:4823-4824`) and
  `DECODE_QKV_GATE_FUSED` (`:5087-5088`) as "not on the default path" is
  inverted — those are precisely the live decode QKV knobs, and they are the
  ones worth screening next on this axis.

## Follow-ups I did not implement (from a frontier code review, unmeasured)

Ranked by the reviewer's 20→40-core argument; all are bit-identical
row-ownership/geometry changes, none is measured here:

1. **Decode attention threadgroup starvation (highest value).** Both fused
   decode-attention kernels bake one threadgroup per *head pair*
   (`head0 = pair_tg*2`, `:1586-1588` sliding, `:2048-2050` full) and dispatch
   `heads/2` TGs of 1024 threads (`:1970-1971`, `:2455-2456`) — 32 TGs sliding
   (64 heads), 24 TGs full (48 heads). On a 20-core M4 Pro that is ≥1 TG/core;
   on 40 M5 cores it leaves 8-16 cores idle with one resident TG each, so the
   kernel's ~2.1-2.6 MB/layer KV stream cannot use the extra bandwidth.
   Remapping to one head per TG (48/64 TGs) leaves each head's 32-simdgroup ×
   16-row partial-sum tree untouched, so it should stay bit-exact. Runs 40×/step.
   This axis is invisible to local M4 timing by construction — it needs an M5
   probe.
2. **`DARKBLOOM_ROUTED_GATEUP_R1=0`** (default ON, `:8053-8054`): 2048 TGs × 1
   row/simdgroup versus 1024 TGs × 2 rows, identical K-block traversal
   (`:7890-7933` vs `:8090-8130`) ⇒ bit-identical. Resident simdgroups/core goes
   102 (M5, R1) → 51 (M5, non-R1), and 51/core is the interior optimum the
   o_proj sweep found. Cheap one-env A/B, second-largest decode byte block.
3. Minor / no expected sign change with core count: the 288-thread fused
   down+residual TG (`:8875-8876`), the LM-head argmax stages
   (`LagunaLmHeadPrune.swift:959-967`), layer-0 dense grids (`:8982-8983`,
   `:9060-9061`).

The same review also offers a mechanism for my confirmed FUSED loss: unfused
routed (2048 TGs) and shared (256 TGs) have no data dependency and are encoded
between the same barriers (`:11141-11143`), so they already co-schedule as one
~2304-TG pool — the fused kernel's grid (`:8245-8246`) is the same size. What
fusion adds is a runtime branch (`if (tg.x < 256) shared; else routed`,
`:8186-8208`) whose compiled pipeline carries the union of both register
footprints, applied to all 2304 TGs including the 2048 bandwidth-bound routed
ones, plus the author's deliberate shared-first ordering (`:8180-8185`) that
displaces 256 routed TGs into the drain tail. +1.42 µs/layer over 39 layers is
~3% of the gate+up phase — the scale of an occupancy notch, not a serialization
change. The reviewer expects fused to still lose on M5 (~+20-30 µs/step) because
both variants stay deep in the many-wave regime, and notes these are
`MLXFast.metalKernel` string kernels, so `_nax` selection is irrelevant to this
comparison.

## 4. Confirm pass `cf2`: the screen's top three, 25 scored runs

Design fixed before the run (prereg addendum): 25 runs at STEPS=224 in a
counterbalanced order giving n = C 8 / RP0 7 / NS2 6 / ASSPA 4, one process per
run, drift-corrected against the interpolated control, paired bootstrap, and a
Bonferroni k=3 (98.3 %) interval because three arms are tested at once.
0 divergences in all 25 runs.

| arm | knob | screen point | confirm point | confirm 95 % CI | Bonferroni 98.3 % | % score | verdict |
|---|---|---|---|---|---|---|---|
| `RP0` | `ROUTER_WEIGHT_PREFETCH=0` | -55.3 | **+5.6** | [-17.3, +29.0] | [-21.4, +34.1] | -0.033 | **not reproduced, no effect** |
| `NS2` | `NVFP4_NIBBLE_SPLIT=2` | +25.3 | **+24.0** | [-1.2, +49.7] | [-6.7, +54.7] | -0.141 | **loss, reproduced twice** |
| `ASSPA` | `DECODE_ASYNC_STAGE=at:0,1,15,31` | -33.0 | +73.5 raw / -36.7 trimmed | [-59.3, +288.7] | [-60.3, +305.1] | - | **undecided, one outlier run** |

Units are us/step; negative is faster. Control run-to-run sd in this pass was
41.5 us/step, so the achieved floor 2sd/sqrt(n) was 31.4 / 33.9 / 41.5 us/step
for n = 7 / 6 / 4.

- **`RP0` is dead.** The screen's -55.3 us/step was noise: seven fresh paired
  runs give +5.6 us/step with the interval straddling zero, and the per-pass
  deltas scatter from -39 to +57 with no structure. The knob is genuinely
  reachable (audit above) and bit-exact, but its shipped default 1 is already
  the right choice. **No default flip is warranted.**
- **`NS2` is a reproduced loss.** +25.3 then +24.0 us/step across two
  independent passes; combined that is a real ~+24 us/step (-0.14 % score)
  penalty for the two-nibble split. With `NS0` also +55.6 in the screen, the
  shipped `NVFP4_NIBBLE_SPLIT=1` is a local optimum on both sides. This closes
  the advisor's priority-1 knob: **keep the default.**
- **`ASSPA` needs its own pass.** Three of its four paired runs are -61.3,
  -57.2 and +8.5 us/step; the fourth is +404 because run 14's median jumped to
  8.606 ms while its immediate neighbours (C 8.220, NS2 8.252) were normal, an
  environmental spike rather than an arm property. Trimming it is post-hoc, so
  the honest statement is "undecided", and this arm is worth the remaining
  probe budget.

### Why sparse async staging is a physically plausible win

The `DECODE_ASYNC_STAGE` arms line up monotonically in the number of staged
layers, which is what a per-stage-point cost with a saturating benefit looks
like:

| stage points | arm | delta us/step |
|---|---|---|
| 0 (`off`) | `ASOFF` | +1140.5 |
| `norm` only | `ASNRM` | +1158.9 |
| 4, `at:0,1,15,31` | `ASSPA` | -33.0 (screen), -36.7 trimmed (cf2) |
| 7, shipped `at:0,1,7,15,23,31,39` | `C` | 0 |
| 12, `at:0,1,3,7,...,39` | `ASDEN` | +12.0 |
| `ladder8` | `ASLAD` | +193.0 |

Staging is clearly load-bearing: removing it entirely costs ~1.15 ms/step,
about 14 % of decode. But past a handful of well-placed points each extra point
adds cost without adding cover. If that shape is real, the shipped 7 points sit
slightly past the optimum and 4 points is the better default.

## 5. Confirm pass `cf3`: sparse async staging at full power

Two arms only, `C` vs `ASSPA`, 24 runs in six ABBA blocks
(`C ASSPA ASSPA C` x 6) so linear drift cancels inside each block, n = 12 each.
At the pass-`cf2` control sd that is an achieved floor of 24 us/step, enough to
resolve a -35 us/step effect. One hypothesis, so no multiplicity correction is
needed and the bar is the plain 95 % interval upper bound < 0 with a point
estimate <= -10 us/step.

Flip hunk if it clears the bar, verified on my base and on the advisor head:

| where | line | current | flip |
|---|---|---|---|
| base `a9de9e8f` `LagunaRuntimeModel.swift` | `747` | `?? "at:0,1,7,15,23,31,39"` | `?? "at:0,1,15,31"` |
| advisor head `18ac6015`, same file | `755` | identical | identical |

Symbol anchor `private let lagunaDecodeAsyncStage: LagunaDecodeAsyncStage = {`
(base :744, advisor head :752). The literal is parsed by the `at:` branch at
base :761-767 into an `.explicit(mask)`, so the flip changes only which layers
stage, never any arithmetic.


### `cf3` result: sparse staging is a small loss, not a win

24 runs, 0 divergences, exit 0. The host was quieter than in `cf2`: control
run-to-run sd 25.8 us/step, so the achieved floor was **14.9 us/step**
(0.087 % score), the tightest of the campaign.

| estimator | delta us/step | % score |
|---|---|---|
| paired mean (drift-corrected) | **+11.1** | -0.065 |
| 95 % bootstrap CI | **[+2.1, +21.3]** | [-0.125, -0.012] |
| paired median (robust) | +7.0 | -0.041 |
| plain median-of-medians (8.216 vs 8.213 ms) | +3.0 | -0.018 |

Per-pair deltas: `[18.7, 46.3, -10.3, -5.7, -0.7, 2.7, 41.7, 20.3, 5.0, 9.0,
10.0, -4.0]`, sd 17.9 us/step.

**`ASSPA` fails the bar in the wrong direction.** The 95 % interval excludes
zero on the positive side, so at this power the honest reading is a small real
regression of +3 to +11 us/step, and certainly not the -35 us/step the two
low-n passes hinted at. Every estimator agrees on the sign.

The low-n hints were driven by control *fast-mode* runs, and `cf3` makes that
visible: the control produced two runs at 8.148 and 8.152 ms while the arm's
best of twelve was 8.206 ms (0 of 12 arm runs below 8.19 ms versus 2 of 12
control runs). A pass that catches one of those control runs next to an arm run
manufactures a 40-60 us/step "win" for whatever arm sits beside it. That is
exactly what happened to `ASSPA` in the screen and in `cf2`, and it is the same
mechanism that produced `RP0`'s -55.3 us/step mirage.

Cross-pass summary for `ASSPA`, best-powered pass last:

| pass | n | point | note |
|---|---|---|---|
| screen | 2 | -33.0 | floor ~78 us/step, uninformative |
| `cf2` | 4 | +73.5 raw / -36.7 trimmed | one +404 environmental spike |
| **`cf3`** | **12** | **+11.1, 95 % [+2.1, +21.3]** | **floor 14.9 us/step, decisive** |

**Conclusion: keep `DECODE_ASYNC_STAGE=at:0,1,7,15,23,31,39`.** No flip was
applied, so this branch ships zero source changes to the scored surface.

## 6. Final disposition of every screened knob

| knob | arm(s) | best evidence | verdict |
|---|---|---|---|
| `SHARED_ROUTED_QMV_FUSED=1` | `FUS` | +55.2 us/step, 95 % [+18.9, +85.9], n=6 | **confirmed loss**, keep default 0 |
| `NVFP4_NIBBLE_SPLIT` | `NS0`, `NS2` | +55.6 (0) and +24.0 (2), reproduced | **default 1 is a two-sided optimum** |
| `DECODE_ASYNC_STAGE` | `ASOFF ASNRM ASSPA ASDEN ASLAD` | sparse +11.1 [+2.1, +21.3]; all others worse | **shipped 7-point mask is the optimum** |
| `ROUTER_WEIGHT_PREFETCH` | `RP0`, `RP5` | 0: +5.6 [-17.3, +29.0]; 5: +25.4 | **default 1 is best**, reachable and bit-exact |
| `OPROJ_ROWS_PER_SIMDGROUP` | `OPR1`, `OPR4` | -64.2 and +1.7 at n=2, floor ~78 | replication only; axis closed by #718/#719 |
| `OPROJ_SIMDGROUPS` | `OPSG4` | -5.4, 95 % [-12.6, +1.6], n=12 (`cf4`) | **no effect**, keep default 2 |
| `DECODE_QKV_GATE_FUSED`, `NORM_AFFINE_QKV_*` | `PF*`, `STG*` | static audit | **inert on this composition**, dead branch |
| `L5_UNROLL` | `U1 U4 U8` | static audit + n=2 | **inert**, no reachable dispatch difference |

Nine shipped defaults were probed on the live composition and every one of them
is already at or better than its neighbours. All three seemingly promising
screen hits evaporated under a properly powered paired confirm, and the
mechanism for the mirage is now identified and documented.

### `cf4`: `OPROJ_SIMDGROUPS=4`, the last unresolved knob

Same design as `cf3`: `C` vs `OPSG4`, 24 runs in six ABBA blocks, n = 12 each,
0 divergences, exit 0. The host was quieter still, control sd 17.9 us/step, so
the achieved floor was **10.3 us/step** (0.061 % score) - the tightest
measurement of the campaign.

- point **-5.4 us/step**, 95 % CI **[-12.6, +1.6]** (+0.032 % score,
  [-0.009, +0.074])
- per-pair deltas `[4.7, -2.7, -7.3, 19.3, -16.0, -10.0, -5.7, 2.7, -19.7,
  -31.3, 1.0, 0.0]`

The interval straddles zero and the point is half the prereg bar, so this is a
**null result**, not a small win. More usefully, the interval **excludes the
screen's -40.9 us/step** outright: whatever `OPSG4` does on this host is
smaller than 13 us/step in either direction, i.e. at most 0.07 % of score.

This does not speak to the M5 case. `OPROJ_SIMDGROUPS` changes how many
simdgroups cooperate per o_proj tile, so its sign depends on the
simdgroups-per-core ratio, and a 14-core M4 Pro cannot reproduce a 40-core
ratio. What `cf4` does establish is that the knob is not a *local* win worth
carrying, and that the screen's apparent -40.9 was the same fast-mode control
artifact documented above. A real answer needs a paired M5 run.

## 7. Method note for the campaign: the n=2 screen tier cannot promote

Three arms produced screen point estimates in the -33 to -64 us/step range and
all three collapsed to null or worse under n>=7 paired confirms:

| arm | screen (n=2) | confirm | n | verdict |
|---|---|---|---|---|
| `RP0` | -55.3 | +5.6, 95 % [-17.3, +29.0] | 7 | null |
| `ASSPA` | -33.0 | +11.1, 95 % [+2.1, +21.3] | 12 | small loss |
| `OPSG4` | -40.9 | -5.4, 95 % [-12.6, +1.6] | 12 | null |

The cause is a bimodal control distribution: this host intermittently produces
control runs 50-70 us/step faster than its own median (8.148-8.152 ms against a
median of 8.213-8.217 ms), and no arm run in 24 paired observations ever reached
that mode. One fast-mode control adjacent to an arm run creates a phantom
40-60 us/step win. Because the screen tier has n=2 and an achieved floor near
78 us/step, it cannot distinguish that artifact from a real effect.

Practical rule for later rounds on this host: treat any screen point estimate
below ~80 us/step as *unresolved*, never as a candidate, and budget n>=10
paired runs in ABBA blocks (achieved floor 10-15 us/step) before spending a
build-and-gate cycle on a flip. Ordering matters as much as n: the ABBA blocks
in `cf3`/`cf4` cut the control sd from 41.5 to 17.9 us/step relative to the
rotating order used in `cf2`.

## 8. Evidence index and reproduction

W&B project `wandb-applied-ai-team/mlxfast-maple`:

| pass | runs | W&B run id | URL |
|---|---|---|---|
| `cf_fus` FUSED confirm | 6 | `6r8i5rcg` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/6r8i5rcg |
| `scr` 13-arm screen | 32 | `cokldr4x` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/cokldr4x |
| `cf2` + `cf3` confirms | 25 + 24 | `ilfrmjpb` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/ilfrmjpb |
| `cf4` confirm | 24 | `4hnxxsb7` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/4hnxxsb7 |

Every pass reported 0 token divergences and exit code 0; no arm ever changed a
generated token.

Reproduction (one arm pass, then its paired analysis):

```bash
env OUT=/tmp/r125e TAG=cf4 STEPS=224 PROFILE=full WARMUP=0 \
    ORDER="C OPSG4 OPSG4 C C OPSG4 OPSG4 C C OPSG4 OPSG4 C \
           C OPSG4 OPSG4 C C OPSG4 OPSG4 C C OPSG4 OPSG4 C" \
    bash research/frieren_r125e_arms.sh
python3 research/frieren_r125e_analyze.py /tmp/r125e/cf4_runs.tsv --confirm OPSG4
python3 research/frieren_r125e_wandb.py /tmp/r125e/cf4_runs.tsv \
    --name r125e-confirm-cf4-opsg4 --stage confirm
```

`research/frieren_r125e_arms.sh` maps each short arm name to its DARKBLOOM env
assignment and calls the prebuilt worker through `research/decode_probe.py`, so
no arm requires a rebuild. `--confirm ARM` prints the paired point estimate, the
95 % interval, the Bonferroni-corrected 98.3 % interval, and the achieved
resolution floor (2 sd / sqrt(n)) so a null can be separated from an
underpowered pass.
