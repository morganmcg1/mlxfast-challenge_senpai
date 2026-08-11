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
stays available for the reverse probe. Note the two o_proj geometry knobs carry
a prior from nezuko R117-C recorded in the doc comment at
`LagunaOProjGeometry.swift:45-52`: `rps=1` measured *worse* on a 20-core M4
(-54.7 vs -83.8 us) but is the M5-relevant point because it reproduces the same
~51 simdgroups/core ratio on 40 cores. My screen re-measures all three on the
**current** composition; a local `rps=1` loss is expected and is not by itself
evidence against the M5 case.
