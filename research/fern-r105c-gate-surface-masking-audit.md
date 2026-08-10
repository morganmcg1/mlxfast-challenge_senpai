# R105-C — gate-surface masking audit

PR #598 · student maple-fern · base `ed1ca05fa48307c45780b31c5d88218480aa9441`
Host: Apple M4 Pro (20 GPU cores, 48 GiB). Worker binary rebuilt from HEAD at
job `dd552b79` (exit 0, 47.8 s).

---

## 0. Preregistration (written before any measurement)

Committed before the A1 trace was run, before the classifier was executed, and
before any receipt was priced.

### 0.1 Hypothesis under test

**H-105C**: the shipped default-ON fusion gates trade GPU parallelism for
dispatch count; that trade was tuned under rule 68's dispatch-cost model and/or
on a narrower machine, so on M5 Max at least one is now net-negative.

### 0.2 Preregistered outcome map (from the assignment §7)

| tag | condition | consequence |
|---|---|---|
| V-DEAD / N-2 | *m* = fraction of the 79 runtime default-ON gates provably dead or masked; **m ≥ 0.25** | advisor §10 "76 unaudited optimizations" retracted as an overcount; §12 shortlist retracted; ledger re-scoped to the live set |
| — | **m ≤ 0.05** | advisor §10 stands |
| N-1 | no live gate has a positive `predicted_gain` | spend **zero** receipts and report that — full credit, modal outcome |
| N-3 | the top-ranked gate's receipt shows a loss | fusion-vs-parallelism trade confirmed correct as shipped ⇒ close the family |
| V-WIN | a live gate's OFF path beats its ON path on M5 with CI excluding zero | flip the default; cross-reference frieren #597 |

### 0.3 Definition of *m*, fixed in advance

Let `G` be the set of runtime default-ON environment gates — every distinct
`ProcessInfo.processInfo.environment["NAME"] != "0"` in `Sources/**.swift` and
`Vendor/**.swift`, minus build-plugin gates (`SPM_CUDA`). The advisor's count is
79; my classifier re-derives it independently and I report both.

A gate `g ∈ G` counts toward *m* iff its **overall class** is one of
`UNREACHABLE`, `MASKED`, or `NO-READ-SITE`. `LIVE` and
`NEEDS-RUNTIME-OBSERVATION` do **not** count. `m = |dead ∪ masked| / |G|`.

This is deliberately the *conservative* denominator and the *conservative*
numerator: `NEEDS-RUNTIME-OBSERVATION` is excluded from the numerator even
though the advisor's prior is that gates 1 and 2 are dead, so *m* cannot be
inflated by my own runtime observation.

### 0.4 Per-site classification rules, fixed in advance

A read site `s` of gate symbol `σ(g)`:

- `DEAD-BRANCH` — `s` sits in an `else` / `else if` branch whose preceding
  chain condition is **exactly** a conjunction of default-ON gate symbols and
  nothing else (so at shipped defaults the earlier branch always wins), or `s`
  is dominated by an early `return` guarded only by default-ON gate symbols.
- `NEEDS-RUNTIME-OBSERVATION` — as above, but the dominating branch carries
  **extra runtime predicates** (shape checks, optional binds, dtype checks) that
  a static pass cannot evaluate.
- `NEG-GUARDED` — `s` is reachable only when another default-ON gate is
  **negated** (`!other`), i.e. off-by-default territory.
- `LIVE` — none of the above.

Overall class = best (most-live) class over the gate's read sites, with
`NO-READ-SITE` when the declared symbol is never read outside its declaration.

### 0.5 Preregistered A1 decision rule (gates 1 and 2)

One `DARKBLOOM_TRACE_FUSION=1` decode run. `LagunaFusionTraceLog.note`
(`LagunaRuntimeModel.swift:79-91`) dedupes, so the instrument reports
**presence/absence of a site**, not a count; per-step counts are derived
separately (see §2.3) and this limitation is stated up front rather than
discovered later.

- `routed+shared down residual` (`:10897`) present **and** `routed down reduce`
  (`:10930`) absent **and** `shared down residual` (`:9064`) absent in the
  decode window ⇒ gates 1 and 2 are confirmed dead at decode ⇒ neither may
  receive a receipt, and I report this in a PR comment immediately (assignment
  §8).
- Any other combination ⇒ gates 1/2 remain live candidates and I say so.

### 0.6 Receipt discipline, fixed in advance

- A gate qualifies for a receipt **only** with a *named mechanism* by which its
  ON path could be slower than its OFF path on a 40-core M5. "Never measured"
  does not qualify.
- Standing hard negatives, not to be spent on: `DARKBLOOM_INVERSE_SCATTER`,
  `DARKBLOOM_ROUTE_COUNTING_SORT` as an isolate.
- Ranking rule (assignment §A7):
  `predicted_gain = occupancy_deficit_ms − (added_dispatches × 2.3403 µs)`.
  Only positive-predicted-gain gates proceed to Phase B.
- Rule 86 is binding: **no `--local-iterate` delta is evidence.** Nothing in
  this report will quote a local-iterate timing delta as support for a gate
  verdict.
- Max 3 receipts (assignment §8). Zero is the expected answer.

### 0.7 What would falsify my own conclusions

- If the classifier's `G` differs from the advisor's 79, the classifier is
  wrong until proven otherwise — I re-derive rather than trust, and I report
  the diff explicitly (assignment §A4).
- Any ⛔ I publish must carry the instrument that produced it and its scope
  (rule 85). A static-only claim is labelled static-only.

---

## 1. A1 — decode fusion trace (gates 1 and 2)

### 1.1 Instrument and command

`DARKBLOOM_TRACE_FUSION=1` makes `lagunaTrace(_:)`
(`LagunaRuntimeModel.swift:79-91`) emit one `mlxfast: fusion active: <tag>` line
to worker stderr the **first** time a tagged site executes. The log dedupes on
the tag string.

That dedup is asymmetric and the asymmetry is what makes A1 decisive:

- **presence** of a tag ⇒ the site fired **at least once** (weak);
- **absence** of a tag ⇒ the site fired **exactly zero times** over the whole
  process lifetime (exact).

A1 only needs the exact half.

```
run_job f06d2615-7da3-4fcd-92f2-92d78bd7eda3   (exit 0, 42.9 s)
env DARKBLOOM_TRACE_FUSION=1 \
  python3 research/decode_probe.py --steps 8 --stderr /tmp/fern_a1_decode8.err
```

`decode_probe.py` drives `.build-worker/release/mlxfast-runtime-worker
runtime-worker --weights weights`: one 512-token prefill (`decode_begin`) and
then 8 real teacher-forced one-token decode steps. Host M4 Pro, 20 GPU cores.
Job stdout:

```
worker up in 42.0s ok=True
decode_begin seed forward: 547.19 ms
teacher-forced greedy tokens: 0 divergences (all match)
first 8 steps (ms): 9.445 8.337 8.305 8.239 8.256 8.180 8.203 8.190
decode steps=8 mean=8.394 ms median=8.247 ms p10=8.180 ms p90=9.445 ms
```

A prefill-only probe (`--steps 0`, job `a0b18f64`) produced the identical fusion
tag set, so the decode-side tags below are already reached by `decode_begin`'s
own trailing single-token work; the 8-step run is the confirmation on real
scored decode steps.

### 1.2 Verbatim trace (all 35 stderr lines, `/tmp/fern_a1_decode8.err`)

```
mlxfast: low-memory startup profile active (physical memory 48 GiB is below the 64 GiB full-profile minimum): capping the MLX allocator cache at 6 GiB and clearing free warmup buffers; compiled decode and every other ranked code path stay enabled; set DARKBLOOM_STARTUP_MEMORY_PROFILE=full to opt out
mlxfast: a machine too small for the model plus the decode working set fails with an out-of-memory error instead of silently skipping ranked code paths; verify on a 64 GiB+ machine or rely on the ranked run
mlxfast: narrow-scales built lane-major pairwise: qkv
mlxfast: narrow-scales built lane-major pairwise: oproj
mlxfast: packed-scales active: shared gate/up halved
mlxfast: packed-scales active: shared down halved
mlxfast: packed-scales active: packed routed gate/up bank prepared
fusion active: lmhead-int5-winner-coarse-v5
mlxfast: lm_head prune active (coarse copy resident)
mlxfast: fusion active: prefill full qk norm+yarn
mlxfast: fusion active: prefill residual+rmsnorm
mlxfast: fusion active: prefill sliding qk norm+rope
mlxfast: fusion active: prefill router tournament
mlxfast: fusion active: prefill fused routed gate/up
mlxfast: packed-scales inactive: packed routed gate/up prefill scale view consumed
mlxfast: packed-scales inactive: packed routed down prefill scale view consumed
mlxfast: fusion active: prefill sorted moe tail
mlxfast: fusion active: last prefill Q+gate / K+V projection banks
mlxfast: fusion active: residual+rmsnorm+router rpg8 pf1
mlxfast: fusion active: decode router top8 (cast sink + norm sink)
mlxfast: packed-scales active: routed swiglu qmv packed dispatch
mlxfast: fusion active: routed gate/up QMV + SwiGLU (packed, producer keys)
mlxfast: fusion active: routed+shared down residual
mlxfast: fusion active: decode embedding+rope atlas
mlxfast: fusion active: decode nvfp4 qkv r1 h48 lane-major
mlxfast: fusion active: attention projection async rung layer 0
mlxfast: fusion active: full qk norm+yarn
mlxfast: fusion active: gated affine oproj nvfp4 qmv h48 lane-major
mlxfast: fusion active: residual+rmsnorm
mlxfast: fusion active: dense gate/up GEMV + SwiGLU
mlxfast: fusion active: dense down GEMV + residual
mlxfast: fusion active: decode nvfp4 qkv r1 h64 lane-major
mlxfast: fusion active: sliding fused attention
mlxfast: fusion active: gated affine oproj nvfp4 qmv h64 lane-major
mlxfast: fusion active: full fused attention
```

(Line 8 genuinely lacks the `mlxfast: ` prefix in the raw file — that is an
upstream inconsistency in the lm-head trace site, not a transcription slip.
`grep -c 'fusion active' /tmp/fern_a1_decode8.err` = 26.)

Targeted grep on the raw file:

```
$ grep -n "routed+shared down residual\|routed down reduce\|shared down residual" /tmp/fern_a1_decode8.err
23:mlxfast: fusion active: routed+shared down residual
```

### 1.3 Verdict on §12 gates 1 and 2 — both dead ⛔

| §12 # | gate | trace tag | site | fired |
|---|---|---|---|---|
| — | `DARKBLOOM_FUSED_ROUTED_SHARED_DOWN_RESIDUAL` | `routed+shared down residual` | LRM:**10922** | **yes** |
| 2 | `DARKBLOOM_FUSED_ROUTED_DOWN_REDUCE` | `routed down reduce` | LRM:**10949** | **never** |
| 1 | `DARKBLOOM_FUSED_SHARED_DOWN_RESIDUAL` | `shared down residual` | LRM:**9065** | **never** |

The preregistered A1 rule in §0.5 fires exactly: tag present, both others absent
⇒ **§12 gates 1 and 2 are dead on the scored path and may not receive a
receipt.**

Correction to the assignment's line numbers (§7.2 / §12): the three trace sites
are at LRM:10922, LRM:10949 and LRM:9065, not :10897, :10930 and :9064. The
gate declarations are at LRM:136-137, LRM:198-199 and LRM:142-144.

**Structural confirmation.** The decode MoE tail is a single if / else-if / else
chain (LRM:10902-10967):

- `if lagunaFusedRoutedSharedDownResidualEnabled, let residual, let downWeight …`
  (LRM:10902-10920) → `lagunaTrace("routed+shared down residual")` at :10922 and
  an **unconditional `return`** at :10923;
- `else if lagunaFusedRoutedDownReduceEnabled, …` (LRM:10934-10947) → :10949;
- `else { … downProj(...) }` (LRM:10958+).

`DARKBLOOM_FUSED_ROUTED_DOWN_REDUCE` is therefore reachable only when the first
branch's *runtime* predicates fail — which is why a purely static pass must
classify it `NEEDS-RUNTIME-OBSERVATION` (§3) and why A1 is required to close it.

`DARKBLOOM_FUSED_SHARED_DOWN_RESIDUAL` is masked one level further out:
`fusedSharedDownResidual` (gate read at LRM:9055, trace at :9065) has exactly
one call site, LRM:11112, inside the *prefill* MoE tail — and its own shape
guard `x.dims(1, 1, hiddenSize)` (LRM:9026) rejects any multi-token prefill row.
Decode never reaches :11112 because the decode branch returns at :10923. This is
an **inter-procedural** mask that no single-function static pass can see.

### 1.4 Per-step counts

`lagunaTrace` dedupes, so counts are derived structurally, not read off the log.
Model shape from `weights/config.json`: 40 layers, `mlp_only_layers = [0]`,
`mlp_layer_types = ["dense", "sparse" × 39]` ⇒ **39 sparse MoE layers**.

| site | per decode step | over the scored 128-step window | over the 512-token prefill |
|---|---|---|---|
| `routed+shared down residual` LRM:10922 | 39 | 4,992 | 0 |
| `routed down reduce` LRM:10949 | **0** | **0** | 0 |
| `shared down residual` LRM:9065 | **0** | **0** | 0 |

### 1.5 Assignment §8 reporting obligation

§8 asks for an immediate PR comment when A1 kills gates 1 and 2. **I have no
typed tool that can post a PR comment**: the student schema exposes
`submit_experiment_result` and `respond_to_human_issue` only, and the harness
forbids reproducing a GitHub mutation with `gh`/REST/`git push`. I am recording
the capability gap here and putting the A1 kill first in the terminal result
summary so it reaches the advisor at the earliest point the protocol allows.

---

## 2. A2 — dispatch-trace differential

### 2.1 Instrument

`research/r103b/scripts/trace.patch` (tanjiro, #572) hooks MLX's Metal
`device.cpp` / `device.h` and writes, per encoded dispatch, a TSV row of
`seq, pipeline_name, kind, grid, threadgroup, arg_shapes`, plus every JIT'd MSL
library. I applied the patch, built the worker with it, then **reverted the patch
from source** (commit `dd3d2f9`); the instrumentation exists only in the
gitignored `.build-worker/` binary, so the submitted surface stayed byte-identical
to the assignment head (`git diff --numstat 5a55425 HEAD -- Sources Vendor` is
empty).

Driver: `research/fern_r105c_trace_arm.sh <arm> [VAR=VAL ...]`, which runs
`.build/release/mlxfast-swift correctness-trace --golden
correctness_prompts/public_longcopy_gate_english_512_256.json --step 5 --top-k 5`
under `env -i` with only the arm's variable added, dumping to
`/tmp/r105c/dump/<arm>/`. Comparison: `research/fern_r105c_compare.py`.

Environment plumbing is real, not assumed: `sanitizedRuntimeWorkerEnvironment`
(`Sources/MLXFastHarness/LagunaRuntimeWorker.swift:1928-1958`) starts from an
empty child environment and copies in an allowlist whose prefixes include
`DARKBLOOM_`. §2.2 below verifies it end to end anyway.

### 2.2 A/A control and positive controls

| arm | env | MSL libs | rows | bytes | md5 | vs `a_base` |
|---|---|---|---|---|---|---|
| `a_base` | — | 103 | 11 244 | 1 671 168 | `4ac08364…` | reference |
| `b_base` | — | 103 | 11 244 | 1 671 168 | `4ac08364…` | **byte-identical** |
| `c_inverse_scatter_off` | `DARKBLOOM_INVERSE_SCATTER=0` | 103 | 11 244 | 1 671 168 | `4ac08364…` | **byte-identical** |
| `d_routed_down_reduce_off` | `DARKBLOOM_FUSED_ROUTED_DOWN_REDUCE=0` | 103 | 11 244 | 1 671 168 | `4ac08364…` | **byte-identical** |
| `e_shared_down_residual_off` | `DARKBLOOM_FUSED_SHARED_DOWN_RESIDUAL=0` | 103 | 11 244 | 1 671 168 | `4ac08364…` | **byte-identical** |
| `f_fused_scatter_off` | `DARKBLOOM_ROUTE_FUSED_SCATTER=0` | **108** | 11 630 | 1 716 224 | `c5cef454…` | **differs** |
| `g_counting_sort_off` | `DARKBLOOM_ROUTE_COUNTING_SORT=0` | **106** | 11 706 | 1 720 320 | `0c595857…` | **differs** |

The A/A control reproduces tanjiro's reference exactly (103 JIT libraries and
11 244 dispatch rows per arm), so the tracer is deterministic on this host.

**Why the positive controls matter.** A null differential is unfalsifiable on its
own: "the trace did not change" and "the variable never reached the sandboxed
worker" look identical. Arms `f` and `g` flip a gate whose OFF branch dispatches a
*structurally different* kernel set, and both change the trace. The plumbing is
therefore demonstrated, not assumed, and the byte-identity of `c`/`d`/`e` is
informative.

`f_fused_scatter_off` (76 = 38 prefill + 38 decode dispatches each):

| kernel | ON | OFF |
|---|---|---|
| `mlx_lm_route_csort_scatter_fused_m8_u32_v4` (grid 8192, TG 256) | 76 | 0 |
| `mlx_lm_route_csort_hist_u32_v1` (grid 4096, TG 128) | 0 | 76 |
| `mlx_lm_route_csort_scan_u32_v1` (grid 256, TG 256) | 0 | 76 |
| `mlx_lm_route_csort_scatter_u32_v1` (grid 8192, TG 256) | 0 | 76 |
| `mlx_lm_inverse_permutation_scatter_u32_v1` (grid 4096, TG 256) | 0 | 76 |
| `gather_frontuint32_uint32_int_1`, `vs_Divideuint32` | 0 | 76 each |

`g_counting_sort_off` replaces the fused kernel with MLX's block-merge argsort
(`sort_mbsort` / `merge_mbsort` / `partition_mbsort`, 76 each) plus the same
`inverse_permutation_scatter`, `gather_front`, `v_copy`, `vs_Divide` tail.

### 2.3 Result: `DARKBLOOM_INVERSE_SCATTER` is a third dead gate

Arm `g` is the direct experimental proof of the advisor's domination claim.
`routeCountingSortFused` (`Vendor/mlx-swift-lm/.../SwitchLayers.swift:263-278`)
guards on **both** `routeFusedScatterEnabled` *and* `routeCountingSortEnabled`, so
`DARKBLOOM_ROUTE_COUNTING_SORT=0` does not measure counting-sort-vs-argsort: it
measures **fused-scatter-vs-argsort**. The non-fused counting-sort kernels
(`csort_hist` / `csort_scan` / `csort_scatter`) appear in arm `f` and are
completely absent from arm `g`. Any receipt that flips
`DARKBLOOM_ROUTE_COUNTING_SORT` as an isolate is mis-attributed by construction.

The same guard structure kills gate 5. In `gatherSort`
(`SwitchLayers.swift:279-300`) the fused branch takes an **early `return`** before
`inversePermutationScatterEnabled` (`SwitchLayers.swift:64`) is ever read. At
defaults the fused branch always succeeds — `n = 512 × 8 = 4096` (prefill rows) is
divisible by the 128-element tile, `m == routeFusedScatterTopK == 8`, and the
prefill routers declare `outputDTypes: [.uint32, .float32]` (LRM:9775-9778,
10161-10164, 10183-10186), satisfying `indices.dtype == .uint32`.

Trace confirmation: `mlx_lm_inverse_permutation_scatter_u32_v1` fires **0 times**
in `a_base`, and **76 times** in each of `f` and `g`. So the read site is
*reachable in principle* and *dominated in practice*:

> **`DARKBLOOM_INVERSE_SCATTER` is DEAD-BY-DOMINATION at shipped defaults.**
> It cannot receive a receipt, and the assignment's listing of it as a hard
> negative is confirmed with a stronger, positive-controlled proof than "the
> timing did not move".

That takes the empirically dead count to **3 of 79** (gates 1, 2 and 5).

### 2.4 Required caveat: an identical trace is not by itself a deadness proof

The tracer records the pipeline name, dispatch kind, grid, threadgroup and
*argument shapes*. It does **not** record the contents of scalar constant
buffers. A gate whose OFF branch changes only a scalar kernel parameter — a tile
count, a stride, a fused-epilogue flag baked into a constant rather than into the
specialised pipeline name — would produce a byte-identical trace while genuinely
changing behaviour and timing.

For the three gates called dead here that loophole is closed by reading the
source, not by the trace alone:

- gate 1 and gate 2 are `if` / `else if` siblings that dispatch *different named
  kernels* (`routed+shared down residual` vs `routed down reduce` vs the unfused
  `downProj`), and A1's `DARKBLOOM_TRACE_FUSION` log independently shows their
  tags never printing;
- gate 5's OFF branch adds an entirely new kernel, which arms `f`/`g` show
  appearing the moment the dominating branch is disabled.

Two further limits of the instrument, stated so nobody over-reads the byte
identity:

1. **Tail truncation.** Every `dispatch.tsv` size is a multiple of 4 096 and every
   file ends mid-row: the trace stream is lost after its last flushed page. Up to
   ~4 KiB (~25 rows) of the end of each run is missing. This is why arms `f`/`g`
   show `+1` on a handful of LM-head and last-layer kernels — a truncation
   artefact of where the page boundary fell, not a behavioural difference. It does
   not affect `c`/`d`/`e`, which truncate at the identical byte.
2. **One golden, one length.** The differential covers a single 512-token prefill
   plus 6 decode steps of one public golden. A gate that only fires on a different
   sequence length or a different mask regime would not show up.


---

## 3. A4 — Tier 2 static reachability over the whole default-ON surface

### 3.1 Method

`research/fern_r105c_gate_classify.py` (committed) parses every
`ProcessInfo.processInfo.environment["DARKBLOOM_*"]` read in `Sources/` and the
listed `Vendor/` files, resolves the Swift symbol each gate is bound to
(top-level `let`, closure-bound `let`, or an `(inline)` use), finds every read
site of that symbol, and walks the enclosing brace structure to decide whether a
*default-ON* sibling earlier in the same `if / else if / else` chain dominates
the site.

Classification labels are the ones fixed in §0.4: `LIVE`, `DEAD-BRANCH`,
`NEG-GUARDED`, `NO-READ-SITE`, `NEEDS-RUNTIME-OBSERVATION`. A gate's overall
class is the weakest label over its sites: a gate is dead only if *every* read
site is dead.

Artifacts: `research/artifacts/fern-r105c/gate-classification.csv` (one row per
gate × read site) and `.json` (per-gate rollup, keyed by
`root_commit = 63bb3e8`).

### 3.2 Cross-check against the advisor's own enumeration

`research/advisor_r105_gate_reachability.py` and this classifier agree exactly on
the surface:

| quantity | advisor script | this classifier |
|---|---|---|
| distinct default-ON `DARKBLOOM_*` names | 80 | 80 |
| … of which runtime gates (drop `SPM_CUDA`) | **79** | **79** |
| distinct default-OFF names | 13 | 13 |
| set difference either direction | none | none |

So the "79 default-ON gates" figure in the assignment title is reproduced
independently before anything is classified.

### 3.3 Static histogram — m(static) = 0/79

| class | count (of 79 runtime default-ON gates) |
|---|---|
| `LIVE` | **76** |
| `NEEDS-RUNTIME-OBSERVATION` | 3 |
| `DEAD-BRANCH` | 0 |
| `NEG-GUARDED` | 0 |
| `NO-READ-SITE` | 0 |

**m(static) = 0 / 79 = 0.0000.** Not one gate on the shipped surface is dead by
*syntactic* domination alone. The three `NEEDS-RUNTIME-OBSERVATION` gates are

- `DARKBLOOM_FUSED_ROUTED_DOWN_REDUCE`,
- `DARKBLOOM_FUSED_RESIDUAL_RMS`,
- `DARKBLOOM_PREFILL_FUSED_RESIDUAL_RMS`.

A1 resolves all three empirically: `routed down reduce` never fires (dead), while
`residual+rmsnorm` and `prefill residual+rmsnorm` both appear in the A1 trace, so
the other two are LIVE. No Tier-3 (A5) work is left over for them.

### 3.4 Why the static number is a floor, not the answer

Both gates A1 killed are invisible to this pass, for two different reasons, and
both reasons generalise:

1. **Runtime-predicate masking.** `DARKBLOOM_FUSED_ROUTED_DOWN_REDUCE` sits in an
   `else if` whose `if` sibling is also default-ON, so the classifier can only
   say `NEEDS-RUNTIME-OBSERVATION`: syntactically the `if` may fail on its
   *value* bindings (`let residual`, `let downWeight`). Only the A1 trace shows
   that at defaults it never does.
2. **Inter-procedural masking.** `DARKBLOOM_FUSED_SHARED_DOWN_RESIDUAL` is read
   inside `fusedSharedDownResidual` (LRM:9055). That function is `LIVE` at its
   own read site; it is the *single call site* (LRM:11112) that is unreachable at
   decode. A per-function pass cannot see this, and the classifier reports
   `LIVE`. It is a false negative of the method, not a bug in the script.

The same holds for `DARKBLOOM_INVERSE_SCATTER` (§2.3): its read at
`SwitchLayers.swift:64` is reached only after an *early return* taken inside the
same function on a different branch, which the domination walk does not model
because the masking construct is a `return`, not an `else`.

**Therefore the honest statement of the audit's headline number is:**

- m(static, syntactic domination only) = 0 / 79 = **0.0000**
- m(empirical, observed dead on the scored path) >= 3 / 79 = **0.0380**

and the second number is a lower bound, because it counts only the gates a trace
actually exercised.


## 4. A3 — Tier 1: the seven gates and every sibling in their chains

Tier 1 is the seven §12 gates plus every gate that shares a chain or guard with
them. Status combines the A1 fusion trace (decode), the A2 dispatch differential
(both phases), and the guard text.

### 4.1 Chain 1 — decode MoE down-projection tail (LRM:10902 / 10934 / 10958)

| branch | gate | decl | trace site | status |
| --- | --- | --- | --- | --- |
| `if` | `DARKBLOOM_FUSED_ROUTED_SHARED_DOWN_RESIDUAL` | LRM:142-144 | LRM:10922 | **LIVE**, 39 / decode step |
| `else if` | `DARKBLOOM_FUSED_ROUTED_DOWN_REDUCE` (§12 gate 2) | LRM:198-199 | LRM:10949 | **DEAD** |
| `else` | — | — | — | not taken |

The first branch's guard is a strict superset match for every sparse layer, so
the `else if` is unreachable at defaults. Confirmed twice: A1 never emits
`routed down reduce`, and arm `d_routed_down_reduce_off` is byte-identical to
`a_base`.

The steady-decode-step profile (§5.1) shows
`laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6` 39x per step, one
per sparse layer, which is exactly the `if` branch. There is no room left for
the other two.

### 4.2 Chain 2 — shared-expert down-residual (LRM:9055 / 11112)

`DARKBLOOM_FUSED_SHARED_DOWN_RESIDUAL` (§12 gate 1, decl LRM:136-137, trace
site LRM:9065) is read inside `fusedSharedDownResidual`. Its single call site is
LRM:11112, inside the `if` at LRM:11217 whose guard is satisfied when
`lagunaFusedRoutedSharedDownResidualEnabled` is also on — and that gate takes
the fused *routed+shared* path instead. Result: the shared-only helper is never
called at defaults. A1 never emits `shared down residual`; arm
`e_shared_down_residual_off` is byte-identical to `a_base`.

### 4.3 Chain 3 — residual + RMSNorm + router (LRM:11172 / 11190 / 11199 / 11213)

| branch | gate | shape guard | status at defaults |
| --- | --- | --- | --- |
| `if` | `DARKBLOOM_FUSED_RESIDUAL_RMS_ROUTER` (LRM:580) | `x.dims(1, 1, hidden)` **and** `mlp is LagunaRuntimeSparseMoEBlock` | **LIVE**, 39 / decode step |
| `else if` | `DARKBLOOM_FUSED_RESIDUAL_RMS` | `x.size == hidden` (single token) | **LIVE but near-dead**: 1 / decode step |
| `else if` | `DARKBLOOM_PREFILL_FUSED_RESIDUAL_RMS` (§12 gate 3) | `x.ndim == 3, x.dim(1) > 1` | **LIVE**, 39 / prefill |
| `else` | — | — | not taken |

Three findings the assignment's §7.2 does not contain.

1. Branches 2 and 3 call the **same** function `lagunaResidualRMSNorm` and
   therefore dispatch the **same** kernel `laguna_residual_rms_bf16_2048_v1`
   (decl LRM:1153). A kernel-identity instrument cannot separate them; only the
   `lagunaTrace` labels (`residual+rmsnorm` vs `prefill residual+rmsnorm`) can.
   They are separated here by shape instead: branch 2 fires at grid
   `512x1x1` (1 threadgroup, one token) and branch 3 at grid `262144x1x1`
   (512 threadgroups, 512 tokens).
2. Branch 1's guard additionally requires a sparse MoE block, so at decode
   branch 2 survives for exactly one layer per step — **layer 0**, the only
   dense layer (`mlp_only_layers = [0]`). Measured: 1 dispatch of
   `laguna_residual_rms_bf16_2048_v1` at `512x1x1` per steady decode step out of
   408 total, i.e. 0.25 % of the step. With
   `DARKBLOOM_FUSED_RESIDUAL_RMS_ROUTER=0` that count becomes 40 (39 sparse + 1
   dense). `DARKBLOOM_FUSED_RESIDUAL_RMS` is a gate that a naive
   "does the kernel appear?" audit would call healthy and that is in fact
   masked in 39 of 40 layers.
3. Branches 1 and 2 both demand a single-token shape, so in prefill branch 3 is
   the *only* reachable branch of the chain. §12 gate 3 is genuinely live and
   carries all 39 prefill sparse layers.

### 4.4 Chain 4 — prefill MoE gate-up / tail (LRM:10977 / 11021, 11071, 11236)

`DARKBLOOM_PREFILL_FUSED_GATE_UP` (LRM:222) and `DARKBLOOM_PREFILL_MOE_TAIL`
(LRM:9669) are both **LIVE** in prefill. LRM:11236 is the only site that makes
`residual` non-nil for the sorted tail, so `DARKBLOOM_PREFILL_MOE_TAIL`
dominates `DARKBLOOM_PREFILL_SORTED_MOE_TAIL` (§12 gate 4): turning the former
off would silently retire the latter. Gate 4 itself is live and clean —
`laguna_prefill_sorted_moe_tail_bf16_v1` fires 76x in the trace at grid
`512x512x1` / threadgroup `256x1x1` = 1024 threadgroups.

### 4.5 Chain 5 — route sort and scatter (`SwitchLayers.swift`)

| gate | decl | status at defaults |
| --- | --- | --- |
| `DARKBLOOM_ROUTE_COUNTING_SORT` (§12 gate 6) | SL:77-78 | **LIVE**, dominates gate 7 |
| `DARKBLOOM_ROUTE_FUSED_SCATTER` (§12 gate 7) | SL:186-187 | **LIVE**, 1 dispatch replacing 6 |
| `DARKBLOOM_INVERSE_SCATTER` (§12 gate 5) | SL:63-64 | **DEAD by domination** |

Proved experimentally in §2. The `gatherSort` early return at SL:285 is the
masking construct for gate 5, and the positive controls
`f_fused_scatter_off` / `g_counting_sort_off` show the instrument can see the
gate's kernel the moment a dominating gate is released.

### 4.6 Tier-1 resolution of the three `NEEDS-RUNTIME-OBSERVATION` gates

A4's static pass left exactly three gates unresolved. All three are now closed
without needing Tier 3 (A5):

| gate | resolved by | verdict |
| --- | --- | --- |
| `DARKBLOOM_FUSED_ROUTED_DOWN_REDUCE` | A1 + arm `d` | DEAD |
| `DARKBLOOM_FUSED_RESIDUAL_RMS` | steady-step profile §5.1 | LIVE (1 / 408 dispatches) |
| `DARKBLOOM_PREFILL_FUSED_RESIDUAL_RMS` | §4.3 shape argument + 39 prefill dispatches at 512 TGs | LIVE |

A5 (Tier 3) was therefore not run; it would have added no information.

## 5. A6 — fusion versus parallelism

### 5.1 The scored decode step, measured exactly

Consecutive `custom_kernel_laguna_decode_embedding_rope_atlas_bf16_2048_v2`
markers bound one decode step. In `a_base` the last three intervals are
identical at **408 dispatches**, so this is the steady state, not a warm-up
artefact. The complete profile (rows 10031-10438):

| n | kernel | grid | threadgroup | TGs | thr/TG |
| --- | --- | --- | --- | --- | --- |
| 41 | `rms` (bfloat16) | 512x1x1 | 512x1x1 | 1 | 512 |
| 39 | `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` | 16384x1x1 | 64x1x1 | 256 | 64 |
| 39 | `laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6` | 147456x1x1 | 288x1x1 | 512 | 288 |
| 39 | `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` | 131072x1x1 | 64x1x1 | 2048 | 64 |
| 39 | `laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1` | 16384x1x1 | 512x1x1 | 32 | 512 |
| 39 | `laguna_prefill_router_tournament_ordinal_norm_active64_v2` | 256x1x1 | 256x1x1 | 1 | 256 |
| 30 | `laguna_sliding_fused_attn_ring_v1` | 32768x1x1 | 1024x1x1 | **32** | 1024 |
| 30 | `laguna_decode_nvfp4_qkv_h64_r1_v1` | 327680x1x1 | 64x1x1 | 5120 | 64 |
| 30 | `laguna_oproj_act_h64_v1` | 16384x1x1 | 64x1x1 | 256 | 64 |
| 30 | `laguna_gate_sp_h64_v1` | 512x1x1 | 64x1x1 | 8 | 64 |
| 10 | `laguna_full_fused_attn_grow_v1` | 24576x1x1 | 1024x1x1 | **24** | 1024 |
| 10 | `laguna_decode_nvfp4_qkv_h48_r1_v1` | 262144x1x1 | 64x1x1 | 4096 | 64 |
| 10 | `laguna_oproj_act_h48_v1` | 16384x1x1 | 64x1x1 | 256 | 64 |
| 10 | `laguna_gate_sp_h48_v1` | 384x1x1 | 64x1x1 | 6 | 64 |
| 2 | `gather_front` bfloat16 | 50176x1x1 | 1024x1x1 | 49 | 1024 |
| 1 each | `laguna_residual_rms_bf16_2048_v1`, `laguna_dense_gate_up_swiglu_bf16_v1`, `laguna_dense_down_residual_bf16_v1`, `laguna_decode_embedding_rope_atlas…`, 4 LM-head kernels, `vn_copy`, `argmax` | | | | |

Sum = 41 + 5x39 + 4x30 + 4x10 + 2 + 10 = **408**. `sdpa_vector` does not appear
at all in a steady step; it exists only in warm-up steps 0-1.

### 5.2 Residency ceiling, scoped to threads per threadgroup

Apple GPU cores retain 96 simdgroups; simd width is 32. The resident-threadgroup
ceiling therefore depends entirely on threadgroup size, which is why an
occupancy claim is meaningless unless it names threads/TG. PR #138's measured
24.0 TG/core at 128 threads/TG is exactly this ceiling.

| threads/TG | simdgroups/TG | TG/core ceiling | machine ceiling M4 (20 cores) | machine ceiling M5 (40 cores) |
| --- | --- | --- | --- | --- |
| 1024 | 32 | 3 | 60 | 120 |
| 512 | 16 | 6 | 120 | 240 |
| 288 | 9 | 10 | 200 | 400 |
| 256 | 8 | 12 | 240 | 480 |
| 128 | 4 | 24 | 480 | 960 |
| 64 | 2 | 48 | 960 | 1920 |
| 32 | 1 | 96 | 1920 | 3840 |

### 5.3 Fusion versus parallelism, per gate, measured on both sides

TG/core is threadgroups divided by core count; "% resident" is threadgroups
divided by the M5 machine ceiling for that threadgroup size. Core counts: M4 Pro
= 20 (this host, measured), M5 Max ~= 40 (ranked host, sensitivity axis).

| gate | side | kernel | TGs | thr/TG | TG/core M4 | TG/core M5 | % resident M5 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `FUSED_FULL_ATTN` | ON | `full_fused_attn_grow_v1` | 24 | 1024 | 1.20 | **0.60** | 20 % |
| | OFF | `full_qk_norm_yarn_bf16_128_v4` | 56 | 32 | 2.80 | 1.40 | 1.5 % |
| | OFF | `sdpa_vector` | 48 | 1024 | 2.40 | 1.20 | 40 % |
| | OFF | `gg2_copy` (x2) | 1 and 256 | 1024 | 0.05 / 12.8 | 0.03 / 6.4 | 0.8 / 213 % |
| `FUSED_SLIDING_ATTN` | ON | `sliding_fused_attn_ring_v1` | 32 | 1024 | 1.60 | **0.80** | 27 % |
| | OFF | `sliding_qk_norm_rope_bf16_128_v1` | 72 | 32 | 3.60 | 1.80 | 1.9 % |
| | OFF | `sdpa_vector` | 64 | 1024 | 3.20 | 1.60 | 53 % |
| | OFF | `gg2_copy` (x2) | 1 and 256 | 1024 | 0.05 / 12.8 | 0.03 / 6.4 | 0.8 / 213 % |
| `FUSED_RESIDUAL_RMS_ROUTER` | ON | `residual_rms_router_rpg8_keys_v1_pf1` | 32 | 512 | 1.60 | 0.80 | 13 % |
| | OFF | `residual_rms_bf16_2048_v1` | **1** | 512 | 0.05 | 0.025 | 0.4 % |
| | OFF | `gemv_al_bm4_bn1` | 16 | 128 | 0.80 | 0.40 | 1.7 % |
| `ROUTE_FUSED_SCATTER` | ON | `route_csort_scatter_fused_m8_u32_v4` | 32 | 256 | 1.60 | 0.80 | 6.7 % |
| | OFF | `route_csort_hist_u32_v1` | 32 | 128 | 1.60 | 0.80 | 3.3 % |
| | OFF | `route_csort_scan_u32_v1` | 1 | 256 | 0.05 | 0.025 | 0.2 % |
| | OFF | `route_csort_scatter_u32_v1` | 32 | 256 | 1.60 | 0.80 | 6.7 % |
| | OFF | `inverse_permutation_scatter_u32_v1` | 16 | 256 | 0.80 | 0.40 | 3.3 % |
| | OFF | `gather_front` uint32 | 4 | 1024 | 0.20 | 0.10 | 3.3 % |
| | OFF | `vs_Divide` uint32 | 4 | 1024 | 0.20 | 0.10 | 3.3 % |
| `PREFILL_SORTED_MOE_TAIL` | ON | `prefill_sorted_moe_tail_bf16_v1` | 1024 | 256 | 51.2 | 25.6 | 213 % |
| `PREFILL_FUSED_RESIDUAL_RMS` | ON | `residual_rms_bf16_2048_v1` | 512 | 512 | 25.6 | 12.8 | 213 % |
| context: routed expert GEMM | ON | `routed_…_top8keys_r1_bf16_v2` | 2048 | 64 | 102 | 51.2 | 107 % |
| context: routed expert GEMM | OFF (via router gate) | `routed_…_packed_bf16_v1` | 1024 | 64 | 51.2 | 25.6 | 53 % |

### 5.4 Measured dispatch counts, both sides

Steady-decode-step dispatch totals and first-prefill-block row totals, taken
from the marker intervals of each arm:

| arm | prefill rows | steady decode step | delta decode | delta prefill |
| --- | --- | --- | --- | --- |
| `a_base` | 7335 | 408 | — | — |
| `f_fused_scatter_off` | 7525 | 408 | **0** | **+190** (38 x 5) |
| `g_counting_sort_off` | 7563 | 408 | 0 | +228 (38 x 6) |
| `h_full_attn_off` | 7335 | 438 | **+30** (10 x 3) | 0 |
| `i_sliding_attn_off` | 7335 | 498 | **+90** (30 x 3) | 0 |
| `j_residual_rms_router_off` | 7336 | 447 | **+39** (39 x 1) | +1 |

`f` changing prefill only and `h`/`i` changing decode only is an independent
confirmation of each gate's phase, and matches the guards.

### 5.5 M5 sensitivity, stated honestly

The only quantity that moves between M4 (20 cores) and M5 (~40 cores) in the
tables above is TG/core: every ON-side threadgroup count is fixed by the model
shape (`heads / 2` for attention, one per layer for the router), not by the
machine. The sensitivity therefore has one shape: doubling core count halves
TG/core, so a kernel that is merely underfilled on M4 becomes *more* underfilled
on M5. `full_fused_attn_grow_v1` at 24 TGs is the extreme: it leaves 16 of 40 M5
cores with no work at all. This is the only genuine occupancy story on the
surface, and §6 prices it.

Two caveats that must travel with this table.

- These traces are M4 Pro (Apple GPU generation 16). The ranked M5 selects
  `_nax` prefill kernels that this host never builds, so every **prefill**
  row above is evidence about the M4 kernel family only. The **decode** rows use
  the same custom kernels on both machines (they are `MLXFast.metalKernel`
  sources compiled from the runtime, not AOT `_nax` variants), so the decode
  geometry transfers.
- Threadgroup *count* transfers; threadgroup *residency behaviour* does not
  necessarily, because occupancy limits also depend on register and threadgroup
  memory use per kernel, which the tracer cannot see.

## 6. A7 — predicted gain

`predicted_gain = occupancy_deficit_ms - (added_dispatches x 2.3403 us)`

The right-hand term is now measured exactly. The scored window is one 512-token
prefill plus 128 one-token decode steps. Local M4 reference times, used only to
express the tax as a fraction: 8.247 ms/decode step (median of 8) so 1055.6 ms
for the decode window, and 547.19 ms for the seed prefill forward.

| rank | gate | phase | added dispatches over scored window | dispatch tax | tax as % of its axis | score cost at zero deficit |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `DARKBLOOM_FUSED_SLIDING_ATTN` | decode | 90 x 128 = 11 520 | 26.96 ms | 2.554 % | -1.92 % |
| 2 | `DARKBLOOM_FUSED_RESIDUAL_RMS_ROUTER` | decode | 39 x 128 = 4 992 | 11.68 ms | 1.107 % | -0.83 % |
| 3 | `DARKBLOOM_FUSED_FULL_ATTN` | decode | 30 x 128 = 3 840 | 8.99 ms | 0.851 % | -0.64 % |
| 4 | `DARKBLOOM_ROUTE_COUNTING_SORT` | prefill | 228 | 0.534 ms | 0.098 % | -0.02 % |
| 5 | `DARKBLOOM_ROUTE_FUSED_SCATTER` | prefill | 190 | 0.445 ms | 0.081 % | -0.02 % |
| — | `DARKBLOOM_FUSED_SHARED_DOWN_RESIDUAL` | — | 0 | 0 | 0 | 0 (dead) |
| — | `DARKBLOOM_FUSED_ROUTED_DOWN_REDUCE` | — | 0 | 0 | 0 | 0 (dead) |
| — | `DARKBLOOM_INVERSE_SCATTER` | — | 0 | 0 | 0 | 0 (dead) |

Score cost uses `score = decode_speedup^0.75 * prefill_speedup^0.25`.

Now the left-hand term, gate by gate.

**Gates with a structurally negative deficit.** For
`FUSED_RESIDUAL_RMS_ROUTER`, `ROUTE_FUSED_SCATTER` and `ROUTE_COUNTING_SORT` the
OFF side is *worse* in parallelism as well as in dispatch count (§5.3): the
router's OFF path collapses to a **single threadgroup** for the RMS, and the
route-sort OFF path's widest kernel matches, never exceeds, the fused kernel's
32 threadgroups. `occupancy_deficit <= 0`, so `predicted_gain < 0`
unconditionally. `FUSED_RESIDUAL_RMS_ROUTER` is additionally not an isolate: it
also downgrades the routed expert GEMM from the `top8keys_r1` variant (2048 TGs)
to `packed_bf16_v1` (1024 TGs), which is a second, larger, uncontrolled change.

**Gates with a possible positive deficit.** Only the two fused attention gates
qualify: ON leaves cores idle (24 of 40, and 32 of 40) while OFF's `sdpa_vector`
uses 48 and 64 threadgroups. The upper bound on the deficit is the *entire*
duration of the fused attention kernels, because the OFF path cannot make
attention take negative time. That duration is bounded by the KV traffic it must
read, which is fixed by the model shape:

- sliding layer, window 512: `2 (K,V) x 512 pos x 8 kv_heads x 128 dims` =
  1.05 MB at 1 byte/element, 2.10 MB at bfloat16.
- full layer, up to 640 positions: 1.31 MB to 2.62 MB.

Per decode step that is 30 x (1.05-2.10) = 31.5-63.0 MB for sliding and
10 x (1.31-2.62) = 13.1-26.2 MB for full. Total decode-step traffic is dominated
by weights: per MoE layer roughly 11.7 MB of QKV, 2.3 MB of O, ~14 MB for the 8
routed experts and ~3 MB shared, so ~1.2 GB per step across 40 layers. Attention
KV is therefore **2.6-5.3 %** of decode-step bytes for sliding and **1.1-2.2 %**
for full.

Setting `occupancy_deficit <= attention_share_of_step`:

| gate | max conceivable deficit (% of decode window) | tax (%) | predicted_gain |
| --- | --- | --- | --- |
| `FUSED_SLIDING_ATTN` | 2.6 - 5.3 % | 2.554 % | **negative unless the OFF path makes sliding attention essentially free** |
| `FUSED_FULL_ATTN` | 1.1 - 2.2 % | 0.851 % | **negative unless the OFF path cuts full attention by more than 39-77 %** |

The OFF path re-reads exactly the same KV bytes, then adds a separate
qk-norm/RoPE pass and two `gg2_copy` materialisations that the fused kernel does
not perform at all. A bandwidth-bound kernel that already streams the same bytes
cannot be sped up by more than the fraction of its time spent *not* waiting on
memory, and 24-48 threadgroups of 1024 threads are on the same side of the
residency ceiling (both below the 120-TG machine ceiling at 1024 threads/TG).
The realistic deficit is a small fraction of the bound, not the bound.

**Conclusion: `predicted_gain < 0` for all seven §12 gates and for every Tier-1
sibling.** No gate proceeds to Phase B.

### 6.1 What the model cannot settle, and why that does not change the answer

The crude makespan model is not reliable in both directions. On this M4 host it
would predict the *opposite* of the shipped default: 24 ON threadgroups on 20
cores needs two waves of 2-head work (4 head-units) while 48 OFF threadgroups
needs three waves of 1-head work (3 head-units), so the model says OFF should
win on M4 — and yet ON is the shipped, measured-faster default. The model is
therefore not the binding constraint; the dispatch tax is, and the dispatch tax
is measured, not modelled.

The one instrument that could price the deficit cheaply — per-kernel `SPLIT=1`
label durations — is blocked. Advisor feedback fb1 (comment 5235290122, rule 82
QUALIFIED 82a/82b) states that label prices are upper bounds with unguaranteed
sign and that the seven gates and their Tier-1 siblings must not be ranked off
them. The two fused attention gates are Tier-2 discoveries rather than named
Tier-1 siblings, but the objection is identical in kind, so this audit does not
rank them off label durations either. Recorded as blocked by 82b.

## 7. Phase B — receipts

**No gate qualified. Zero M5 receipts were drawn.** This is preregistered
outcome **N-1** from §7 of the assignment.

Three independent reasons, any one of which is sufficient:

1. **A7 arithmetic.** `predicted_gain < 0` for every gate on the surface (§6).
   The assignment's Phase B rule is that only a positive `predicted_gain`
   proceeds.
2. **Hard negatives already excluded two of the seven.** `DARKBLOOM_INVERSE_SCATTER`
   is dead, and `DARKBLOOM_ROUTE_COUNTING_SORT` is not an isolate. A1 and A2 then
   killed two more (`FUSED_SHARED_DOWN_RESIDUAL`, `FUSED_ROUTED_DOWN_REDUCE`).
   A gate that never executes cannot be net-negative.
3. **Coordination.** The assignment records that frieren (#597) and nezuko
   (#584) are spending M5 receipts on decode-side dials this round and instructs
   this experiment to keep decode dials at shipped defaults. The only gates with
   any named mechanism at all (`FUSED_SLIDING_ATTN`, `FUSED_FULL_ATTN`,
   `FUSED_RESIDUAL_RMS_ROUTER`) are decode dials. Drawing a receipt on them would
   confound two live experiments to test a hypothesis whose own arithmetic
   already predicts a loss.

The correctness instruments that a receipt would have required were therefore
not run either: no non-bit-exact gate (§12 gates 2 and 3) was perturbed in any
submitted commit, and `git diff --numstat 5a55425 HEAD -- Sources Vendor` is
empty for the whole branch. All measurement in this report was done with
environment variables against unmodified submitted sources, plus a research-only
MLX tracer that was reverted in `dd3d2f9` and never entered a timed run.

## 8. Corrections to the assignment's §7.2, and the evidence contract

### 8.1 Corrections and additions

1. **Line numbers.** The trace sites are LRM:9065 (`shared down residual`, not
   :9064), LRM:10949 (`routed down reduce`, not :10930) and LRM:10922
   (`routed+shared down residual`, not :10897). Declarations are LRM:136-137,
   LRM:198-199 and LRM:142-144.
2. **§12 gates 1 and 2 are dead, not "very likely masked".** Measured twice
   (A1 trace and byte-identical A2 arms `d`, `e`). Advisor's prior confirmed and
   upgraded from likely to observed.
3. **§12 gate 5 is dead by *domination*, not "provably unreachable".** The read
   site at `SwitchLayers.swift:64` is perfectly reachable; what masks it is the
   early `return` inside `gatherSort` at SL:285 taken on the fused branch.
   Releasing either dominating gate makes
   `inverse_permutation_scatter_u32_v1` fire 76 times immediately (arms `f` and
   `g`). The operative claim — dead at shipped defaults — stands; the mechanism
   in §7.2 does not. This distinction matters because an "unreachable" gate can
   be deleted while a "dominated" gate cannot.
4. **§12 gate 6 dominates gate 7: confirmed experimentally.** With
   `DARKBLOOM_ROUTE_COUNTING_SORT=0` **no** `route_csort_*` kernel of any kind
   appears in the trace, so that arm measures fused-counting-sort versus
   multi-block argsort, not gate 7's contribution. Gate 6 is correctly excluded
   as a Phase B isolate.
5. **Dispatch deltas, measured rather than derived.** Gate 7 is ON = 1 dispatch
   versus OFF = 6 (advisor derived 2 versus ~7), i.e. +190 per 512-token prefill
   over 38 sort sites. Gate 6 is +228 (+6 per site). Gate 4 ON = 1 dispatch is
   confirmed; its OFF side was not measured (no arm was spent) so the advisor's
   OFF = 2 remains underived here.
6. **The residual-RMS chain needs three corrections.** Branches 2 and 3 share
   one kernel, so kernel identity cannot separate them (§4.3). Branch 3 is the
   only branch reachable in prefill, so §12 gate 3 is unambiguously live.
   Branch 2 (`DARKBLOOM_FUSED_RESIDUAL_RMS`) survives at decode for exactly one
   dispatch out of 408 per step — the dense layer 0 — and is masked in all 39
   sparse layers. §7.2 does not list it and a naive audit would score it healthy.
7. **`DARKBLOOM_FUSED_RESIDUAL_RMS_ROUTER` is not an isolate.** Turning it off
   also swaps the routed expert GEMM from `top8keys_r1_bf16_v2` (2048 TGs, grid
   131072) to `packed_bf16_v1` (1024 TGs, grid 65536). Any future ablation of it
   moves two mechanisms.
8. **Terminal prefill row.** `callLastPrefillRow` (LRM:11685, taken only when
   `h.dim(1) > 1` and the mask is `.causal`) does put the last layer's terminal
   prefill row on the decode-shaped MoE branch, so gate 1's "decode +
   terminal-prefill-last-row" description is structurally right. It is
   nevertheless dead, because the decode occurrences are zero and the prefill
   occurrence is a single row on a branch the routed+shared gate takes first.
9. **There is no 1 671 168-byte trace quota.** That figure in the assignment
   (from tanjiro #572) is a coincidence of two runs emitting identical traces.
   The real instrument limit is the unflushed final page: `dispatch.tsv` sizes
   are always multiples of 4096 and the file ends mid-row, so up to ~25 trailing
   rows are lost. This is the sole cause of the spurious +/-1 counts on last-layer
   and LM-head kernels in the differential tables, and it never affects a
   steady-state interval.

### 8.2 Evidence contract (§6 of the assignment)

| item | where |
| --- | --- |
| 1. report with preregistration written before measurement | §0, commit `63bb3e8` (first commit on the branch) |
| 2. A1 verbatim lines, per-step counts, verdict | §1 |
| 3. A4 machine-readable classification, script, and *m* | §3, `research/fern_r105c_gate_classify.py`, `research/artifacts/fern-r105c/gate-classification.{csv,json}` |
| 4. A6 table with M5 sensitivity | §5 |
| 5. A7 ranked list with arithmetic | §6 |
| 6. Phase B receipt table or explicit "no gate qualified" | §7 — **no gate qualified** |
| 7. W&B run with result marker and artifacts | §9 |
| 8. corrections to §7.2 | §8.1 |

### 8.3 The headline number against the preregistration

- m(static, syntactic domination only) = 0 / 79 = **0.0000**
- m(empirical, observed dead on the scored path) = 3 / 79 = **0.0380**
  (`FUSED_SHARED_DOWN_RESIDUAL`, `FUSED_ROUTED_DOWN_REDUCE`, `INVERSE_SCATTER`)

Both are far below the 0.25 threshold at which §10 and §12 would be retracted,
and at or below the 0.05 threshold at which they stand. **The advisor's §10
stands.** The gate surface is not meaningfully padded with dead switches: 76 of
79 default-ON runtime gates do real work, and the three that do not cost nothing
because they never execute.

The near-dead case found in §4.3 is worth more than the dead ones: a gate can be
live at 1/408 of a decode step while a reader of the source would assume it
carries 40 layers. Counting read sites, or even counting kernel appearances,
does not measure a gate's weight. Only the steady-state interval does.

### 8.4 Suggested follow-ups, not implemented

1. **Re-tune the fused attention head pairing rather than flipping its gate.**
   Both fused attention kernels hardcode `grid: ((heads / 2) * 1024, 1, 1)` with
   a 1024-thread threadgroup (LRM:1969 sliding, LRM:2458 full). That `/ 2` is
   what produces 24 and 32 threadgroups. Emitting one head per threadgroup would
   give 48 and 64 threadgroups — the same occupancy as the OFF path — while
   keeping the single fused dispatch and paying none of the 27 ms dispatch tax
   measured in §6. This is the named mechanism of this audit implemented as a
   geometry change instead of a gate flip, and it is the single most promising
   thing this report found. It needs an M5 receipt because §6.1's makespan model
   is unreliable on M4.
2. **Price the `top8keys_r1` routed GEMM variant separately.** §5.1 shows it at
   2048 threadgroups of 64 threads, 107 % of the M5 residency ceiling, and it is
   the largest single dispatch family in the decode step. Its non-keyed sibling
   uses half the threads for the same work.
3. **The router tournament kernel runs at 1 threadgroup.**
   `laguna_prefill_router_tournament_ordinal_norm_active64_v2` dispatches grid
   `256x1x1` with threadgroup `256x1x1` — one threadgroup, 39 times per decode
   step, i.e. 39 of 408 dispatches each using 1/40th of the machine. Whether it
   can be batched across layers is out of scope here but is a real serialisation.
4. **Retire `DARKBLOOM_INVERSE_SCATTER` deliberately or document it.** It is
   dead at defaults but reachable under a legal environment, so it is not free to
   delete; #558's 4 186-byte cost claim applies to it unchanged.

