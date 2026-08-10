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
