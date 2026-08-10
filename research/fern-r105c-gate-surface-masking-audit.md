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
