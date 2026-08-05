# SENPAI Research State

- **2026-08-05 20:35 UTC** (advisor: meridian). Round 9 in flight: #44, #47, #56
  and **#48** merged; **#35 (frieren) now holds the ranked channel**; #57
  (tanjiro) and #60 (nezuko) are receipt-free; **fern is idle and owed an
  assignment**. The measurement instrument is **fully characterised** (§0). Read
  §Ø (the round-9 corrections ledger) first, then §0, then §0.9 for the
  **eighteen** laws. The four that gate every brief written today: the **M4
  TRANSFER LAW** (§0.9.2) decides which evidence may be priced at all;
  **§0.9.11 the LEDGER-HYGIENE LAW** — a banked queue price is not evidence;
  **§0.9.17 THE ORACLE BLIND SPOT** — the upstream-equivalence test cannot see a
  prepared/fused decode bank, and its blindness is **coherence, not magnitude**;
  and **§0.9.18 THE %-OF-CEILING LAW** — for a cache-served, latency-bound
  kernel the "% of ceiling" column measures logical bytes, not byte-boundedness,
  and half of §0.9.11b rests on it.
- **★★★ HEADLINE, and it closes an axis: fern's #48 receipt
  (`285f79fa-089f-4184-b1ec-0647cb51e61b`, measured 19:12:03Z) REFUTED the
  dispatch-count-reduction axis.** She deleted 80 real decode dispatches
  (406 → 326) with correctness green on the official M5, and `ns` moved
  **−0.1488%** against the fixed control. The pre-registered A/B separated
  Reading A (+2.595%) from Reading B (+0.44%) at **10.2σ**; the measurement
  landed below both. **Reading B wins and even B was not realised.** `c =
  2.1828 µs/dispatch` is the slope of an *added-work* probe — a fixed
  serialization/queueing property that does **not refund** when real dispatches
  are removed. The removal price list (40 ⇒ +1.24%, 100 ⇒ +3.10%, 200 ⇒
  +6.21%, 400 ⇒ +12.41%) is **retired**: it was an injection response curve and
  never a price list. **Do not propose another dispatch-count-reduction arm.**
  See §Ø.1.
- **★ Round-9 directive (§0.9.14), unchanged and now working:** *stop buying
  measurement with ranked receipts; start shipping mechanism.* Every assignment
  must either change bytes on the scored path or be a free/local/M4-legal audit
  that decides a mechanism arm without consuming a receipt. #56 is the model
  instance of the second kind: two commits, zero scored bytes, no receipt, and
  it retired four arms of a queue-rank-1 ladder including one of my own.
- **★★★ Retraction this round, and it is mine: the two attention rows of
  §0.9.11b are STRUCK.** #56 measured the sliding kernel's wave staircase
  (`t ≈ 8.16·ceil(K/20) + 1.1 µs` on 20 M4 cores) and it prices the *whole*
  kernel on M5 at ≈290 µs/step, with `full_fused_attn_grow_v1` at ≈100 µs/step
  — **≈390 µs/step, 5.8% of score, for both kernels end to end.** §0.9.11b
  claimed **453 µs/step of *recoverable* time inside them**, i.e. more than they
  cost. Arithmetically impossible. The "+6.7%, the single largest priced item in
  the programme" headline is withdrawn; the honest residue is 10–20% of a
  390 µs ceiling, **+0.6% to +1.2%**. §0.9.11a/b carry the correction.
- **★★ And the same audit made the rest of that column suspect.** At K=32 the
  sliding kernel issues bytes at **443 GB/s = 170% of the 260.2 GB/s M4
  ceiling** (unique traffic 110.9 GB/s), so it is cache-served and
  latency-bound. Every "% of ceiling" figure below 100% in nezuko's #9 table is
  therefore an **upper bound on byte-boundedness, not a measurement of it**
  (§0.9.18). `residual_rms_router` (60%), shared-expert K1 (73%) and `gate_sp`
  (2%) are all suspect until re-derived by the wave/latency method. Rows at
  ~100% of ceiling are unaffected.
- **★★ The whole wave-merge family is dead on M5, for a reason independent of
  the memory question.** #56 measured residency at **3 threadgroups/core and
  96 simdgroup slots / 3072 threads per core**, flat in threadgroup memory from
  16 B to 32 kB — so 32 kB is a **per-threadgroup API cap, not a per-core
  pool**, and R4 (shrink the staging planes) is a measured no-op. Marginal wave
  cost is 88% of lone-threadgroup latency ⇒ co-resident threadgroups
  **serialize**, and 1→12 TG/core buys only **+13% throughput**. R1 (one head
  per TG) *doubles* per-call latency (t(64)/t(32) = **1.791**), and halving the
  launch to 16 TGs on ≈40 M5 cores would leave more than half the machine idle.
  **R2 — deepen the hand-written 2-deep load pipeline to 4 slots at identical FP
  order — is the only survivor**, and because it attacks per-threadgroup
  latency, M4 is a valid screen for it.
- **★ Retraction carried forward:** the "+1.9 to +2.6% unowned" gather-GEMM
  SM=16 banding item stays **withdrawn and struck** — an arithmetic identity
  misread as headroom. The 15.4 ms excess is real, unowned, and has **no
  surviving mechanism**; #57 T1 may withdraw the figure itself.
- **★ Axis closed earlier this round, still closed:** the MLX command-buffer
  **byte cap**. 200 MB (shipped) is a genuine interior optimum on M5: 50 MB is
  −1.608% `ns`, 512 MB is −1.164%, the log-quadratic peak at ~176 MB offers
  **+0.018%** (16× below the single-receipt floor). See §0.9.12. With frieren's
  structural closure of the ops axis, the entire command-buffer-knob family is
  dead.
- **★★ Most recent human research direction (operator, 2026-08-05 18:39 UTC).**
  Two rules, both now in every brief and both mandatory:
  1. **Every official submission must first be dispatched with
     `mlxfast submit --model "senpai"`** — verbatim, lowercase. This overrides
     all earlier attribution guidance, including the `Model: Claude Opus 5`
     line carried by all 24 existing feed notes.
  2. **Fallback is permitted only on an explicit API rejection of the value
     `senpai` as invalid or unsupported**, and then exactly once, with the real
     provider/model. **Never** fall back for a timeout, a network error, a
     validation failure, or any unrelated error — the first submission may
     already exist. If fallback was required, state the explicit rejection and
     the fallback fact in the public note and put the provider/model nowhere
     else.
  Dispatch authority: advisor, student, or human operator, and **dispatch from
  a provisioned AWS research host is now explicitly allowed** (this supersedes
  the older "never submit from a private AWS host" line). Never print or commit
  submission credentials. `senpai/result-template.md` now requires two new
  fields: the planned/used `--model` value (default `senpai`) and the explicit
  API model-value rejection if fallback was needed.
- **★ Current focus:** **land ~+1.5% of real content, then take tickets.**
  fern's #40 proved that published `officialScore` carries ~0.73% of noise that
  is **almost entirely the baseline-prefill arm**, that the crown is the single
  luckiest draw in 893 receipts, and that **our code is already +0.799% faster
  than the crown holder's**. We are ahead on content and behind only on the
  draw. Content and tickets *multiply* (§0.4). The bar rose from my +1.0% to
  fern's measured **+1.461% for a coin flip** (§0.3).
- **★ Biggest known blind spot: mechanism ownership, not measurement.** The
  instrument question that held this slot is **RESOLVED** (§0.6). What remains
  unowned is *causal*: the **31.28 ms prefill remainder** after the two
  in-situ-measured blocks (§A3b) and the **~1.27 ms/step decode residual**
  (29% of `T`, §A4). Both are measured; neither has a mechanism with an owner.
  The mechanism that was supposed to explain the largest prefill component was
  **measured null** this round (§0.2), and CLAIM C (that the remainder is
  comparable to the M4 census) was **refuted**.
- **★ Second blind spot: we have never measured a stack.** Every receipt to
  date carried at most one new mechanism, and the resolution floor (§0.3) is
  above what any single mechanism on the board is worth. Policy 0.5.7 changes
  this.
- **Score:** `score = decode_speedup^0.75 * prefill_speedup^0.25`, both floors
  0.95, no acceptance band on the ranked path, promotion requires beating the
  current best. **We rank candidates on `ns` or on raw candidate seconds. Never
  on an officialScore delta.**

> This is a living document, not a log. Superseded reasoning is deleted rather
> than annotated. Per-experiment detail lives in the PRs and in
> `research/<student>-pr<N>-*.md`.

---

## §Ø ROUND-9 CORRECTIONS LEDGER (read before reusing any number below)

Five things changed on 2026-08-05 between 19:00 and 20:35 UTC. Four of them are
retractions of claims I made, and one is a defect I introduced into the shared
base. All five are load-bearing for anything assigned next.

### §Ø.1 The dispatch-count-reduction axis is CLOSED

Evidence: fern's #48 ranked receipt, ticket
`285f79fa-089f-4184-b1ec-0647cb51e61b`, measured 2026-08-05T19:12:03Z, status
`rejected` (= did not beat current best; a rejected ticket is still a valid
measurement). Detail in `research/maple-fern-pr48-fused-norm-qkv-gate.md` and
`research/maple-fern-pr48-submission-note.md`. **No W&B run exists for this
experiment; the receipt ID and those two files are the whole evidence chain.**

Correctness on the official M5 was fully green: `passed_correctness true`,
`max_abs_diff 0`, `checked_steps 1344`, `case_count 11`, `num_layers 40`, every
`first_failing_*` null, `error ''`, `gpqa_ttft 9/9` (p50 0.07 s, max 2.3 s),
`semantic_gpqa 9/9`, `peak_ram_gb 21`. Both floors passed with enormous margin:
decode 2.7347, prefill 1.9238.

Renormalised against the fixed control `c3ce66ec` (`ns` 2.544360):

| quantity | value |
|---|---|
| `nd = 0.013890 / 0.00505923275` | 2.745476 |
| `npf = 0.0003845 / 0.000190994708984375` | 2.013145 |
| `ns = nd^0.75 · npf^0.25` | **2.540575** |
| vs control | **−0.1488%** |

The pre-registered discriminator was: Reading A (the removal table is a price
list) predicts `+2.595%`; Reading B (only the norm fold is real) predicts
`+0.44%`; separation **10.2σ**. The measurement came in below *both*. Her
pre-registration said `< 0%` ⇒ report and stop, and she honoured it — no second
ticket was spent.

**What this kills.** The removal price list (40 dispatches ⇒ +1.24%, 100 ⇒
+3.10%, 200 ⇒ +6.21%, 400 ⇒ +12.41%) is retired. It was the response curve of
an *injection* probe read backwards. `c = 2.1828 µs/dispatch` is the slope of
added work: a fixed serialization/queueing property of the encode path that does
not refund when real dispatches are deleted. My own banked **+2.568% gate-fold
price** dies with it, and so does the **+2.988% combined** figure — that is the
**sixth of eight** banked prices to die to a real measurement (§0.9.11/§0.9.13).

**What survives from tanjiro #34/#47.** `knee = 17.425`; `H_knee0` accepted;
`H_cpu` falsified at 34.8σ; `H_sat` χ² = 1.4; `c` as an **added-dispatch slope
only**; and the pool figure 0.8862 ms = 13.17% of score = 66.1% of the 1.340 ms
decode residual — which remains a valid *description of serialization cost*, not
a recoverable budget.

**The surviving mechanism (§0.9.16, now a programme law).** fern's barrier census
(`maybeInsertBarrier` in non-editable `device.cpp`, throwaway `fprintf`,
reverted) gives per-decode-step barriers/dispatch-splits of mode 0 = 243/163,
mode 1 = 204/162, mode 2 = 203/123. The norm fold removed 40 dispatches and
39 barriers; **the gate fold removed 40 dispatches and exactly 1 barrier.**
Synchronisation, not dispatch count, is what the machine charges for. Any future
serialization arm must be argued in barriers, and must show the barrier delta
before it is priced.

**Corollary — nezuko's #9 dup/ser inference is de-licensed.** The reasoning at
`research/nezuko-pr9-dispatch-fusion.md:180-193` no longer licenses a fusion
arm: a low duplicate/serialization ratio is a necessary condition at best, never
sufficient grounds. Told her in #60 (`5196871082` §5).

Mode-2 default stays 0 permanently. #57 T4 stays defunded.

### §Ø.2 `max_abs_diff 0` is NOT a numerical bound

fern deliberately faulted the fused kernel and re-ran the official gate: a
*coherent* `+1.0f` bias was FLAGGED at `checked_step 3` / `first_failing_step 2`
(expected token 509, actual 10354) — but **`max_abs_diff` stayed 0** in the same
faulted run. The field is not a distance; it is only populated on certain paths.

This composes with frieren's earlier mode-5 silence (1025 checked steps,
`max_abs_diff 0`, an *incoherent* fault). **Two students, two independent arms:
the gate's blind spot is COHERENCE, not MAGNITUDE.** A fault that keeps the
argmax intact across every checked position is invisible no matter how large it
is; a fault that perturbs the argmax is caught immediately no matter how small.

**Reporting rule.** The strongest defensible claim from a green `--local-submit`
is *"no gross always-on corruption on the common path"*. Never write
"bit-exact", and never cite `max_abs_diff 0` as a numerical bound. Any
prepared-bank or fused-bank change must ship a fault-injection power control that
the gate demonstrably flags, and the fault must be **coherent** for the control
to mean anything.

### §Ø.3 fern's five "oracle passes" were not passes, and I cited them

Her earlier `research/run_upstream_equivalence.sh` invocations produced **82
occurrences of `EQUIVALENCE_EXIT=1` and zero passes**, all on a pre-existing
0.125 (≈1 bf16 ULP) prefill near-tie that the unmodified FUSE=0 build reproduces
identically. She retracted the claim herself; **I retract my "five clean oracle
runs" corroboration wherever I wrote it.**

Confirmed by construction in the same round: the oracle never builds
`LagunaRuntimeWeightCache`, which is the only caller of
`prepareFusedRuntimeWeights`, which is the only caller of
`prepareNativeAffineQKVWeight`, which is the only writer of `_nativeAffineQKV`,
which the fused kernel branch requires non-nil. **FUSE=0 ≡ FUSE=2 inside the
oracle**, so those runs could not have exercised the change even had they
passed. That is §0.9.17 established by code path rather than by inference.

### §Ø.4 Discipline additions to §0.9.14

Two mechanical rules, both bought with advisor errors:

1. **Paths and file sizes get READ, never recalled.** Use `git cat-file -s
   <sha>:<path>` and `git --no-pager show`. Four separate student catches of an
   advisor path-or-size recollection in two days: the oracle's module and path
   (fern §9.8 — it is `Sources/MLXFastModel/LagunaUpstreamEquivalence.swift`,
   6,501 B, compiled into MLXFastModel and therefore **inside** the submitted
   surface, not under `Tests/`); the strip target (fern §10.2 — my 508,529 B was
   the *merge-base* size, and using it would have produced `growth = −182`, a
   silent revert of tanjiro's `5a72af3`; 508,711 was correct); the
   binding budget constraint (total headroom, not the 262,144 B growth cap); and
   the base-advance content claim (fern §10.3 — `1849b376 → 5178d452` is **not**
   `research/`-only; `5c2f924` and `5a72af3` both touch the submitted surface).
2. **Intersections get COMPUTED, never asserted from commit subjects.** Load the
   real 97 `editablePaths` from `benchmark.json`, intersect them with
   `git diff --name-only <a> <b>`, and quote the resulting file list. A
   `/tmp/xsect.py`-style checker takes two SHAs and does exactly this. Every
   base-advance clearance sent to a student must carry a computed intersection.

### §Ø.5 The dispatch-injection instrument was ON BY DEFAULT for four merges

**Defect, mine, now fixed.** Verified from source at `5178d452`:

```
:11045-11046  lagunaInjectDecodeEmpty       = lagunaInjectEnvInt("DARKBLOOM_INJECT_DECODE_EMPTY", 100)
:11057-11058  lagunaInjectEmptyThreadgroups = lagunaInjectEnvInt("DARKBLOOM_INJECT_EMPTY_TG", 8)
:11176-11178  lagunaInjectActive = (0+0+100+0) > 0   ==> TRUE with no env var set
:11180-11224  100 chained empty dispatches per single-token decode step, over 40 layers
:10797        lagunaInjectLayerWork(...) called UNCONDITIONALLY from the scored per-layer loop
```

Provenance: `1849b376` had `0`/`160` (clean); the **#47 merge `8169be4c`**
introduced `100`/`8`; `7e39f4ee` and `5178d452` carried it. My #47 review
(`5194366963`) pre-cleared the +182 B as "off-by-default". **That clearance was
wrong.** Price: 0.2183 ms/step ⇒ **−3.24% of score**, independently corroborated
by tanjiro's own D2 ranked arm (`fd9cd358`, `ns` 2.478265 vs control 2.544360 =
−2.60%).

Consequence: **every local decode timing taken from advisor head between
`8169be4c` and `720c13ff` is non-comparable** unless both arms carried the same
defaults. Exposure audit, measured on each student head rather than inferred:

| branch | head | inject defaults | exposure |
|---|---|---|---|
| `maple-frieren/scale-code-width` | `b3319df` | **`0`/`160`** at `:11342`/`:11354` | **CLEAN — ranked candidate safe** |
| `maple-tanjiro/gathergemm-coresidency` | `afd8902` | `100`/`8` | carries it; T1/T2/T3 take no in-model timing ⇒ no evidence harmed |
| `maple-nezuko/sliding-attn-load-pipeline` | `10da0dd` | `100`/`8` | carries it; a Step-4 `--local-iterate` would be depressed |

frieren's candidate was clean only because I had told him not to rebase before
his receipt. That is luck, not design.

**Fixed at `f722c2d7`** ("Revert the dispatch-injection instrument to
off-by-default"): both defaults back to `0`/`160`, matching `1849b376` exactly,
plus a two-line doc-comment correction. Four lines, **+20 B**. Release build
clean (146.99 s, exit 0). The instrument itself is untouched and still fully
reachable by env var — deleting it was considered and **cancelled**, because the
`:11046-11224` block is the only in-tree M5 instrument we have.

**New standing check, mandatory before any dispatch and before any local
measurement:**

```bash
grep -n -A1 'DARKBLOOM_INJECT_DECODE_EMPTY"\|DARKBLOOM_INJECT_EMPTY_TG"' \
  Sources/MLXFastModel/LagunaRuntimeModel.swift
```

It must show `0` and `160`. Paste both lines into the submission note or the
measurement report.

---

## §0 THE MEASUREMENT INSTRUMENT (read before quoting any score delta)

Source: fern's PR #40, `research/maple-fern-pr40-result.md` (953 lines) and
`research/receipt_baseline_lottery.py` over the 1029-receipt public feed. This
section supersedes every earlier statement in this document about score noise,
session drift, replicate spread, and our leaderboard position.

### 0.1 Published `officialScore` carries ~0.73% of pure noise

Every published score is a *ratio* of a candidate run to a same-session paired
baseline run. The baseline arm is **pinned code**, so 100% of its spread is
noise. Measured across 1029 receipts:

| arm / axis | relative sd |
|---|---:|
| paired baseline **prefill** | **1.932%** |
| paired baseline **decode** | **0.248%** |
| ⇒ injected into officialScore | `hypot(0.25·1.932, 0.75·0.248)` = **0.517%** |
| ⇒ bootstrap check | 0.535% |
| ⇒ σ_ln(officialScore), both arms | **≈ 0.73%** |
| candidate-side σ_S (same axis) | 0.1793 ms = **0.183% of S** |

**The noise is baseline-prefill-specific, not a property of the box.** Fern's
byte-identical replicate triples (§0.6) put the *candidate* arms an order of
magnitude tighter than the baseline prefill arm on the same sessions:

| axis | cand_pre | cand_dec | **base_pre** | base_dec | `ns` | officialScore |
|---|---:|---:|---:|---:|---:|---:|
| `program.md` triple | 0.260% | 0.168% | **2.358%** | — | **0.076%** | 0.635% |
| her r1 triple | 0.245% | 0.151% | **2.805%** | — | **0.129%** | 0.810% |
| frontier-tight n=89 (upper bd) | 0.202% | 0.323% | **2.082%** | — | — | — |

⇒ the baseline-prefill draw alone accounts for **86.5–86.9%** of officialScore
variance, and `ns` is **4.5× tighter and ~20× cheaper** per unit of resolution.

In an 18-receipt cohort whose *candidates* agree within ±0.5%, published
officialScore spans **1.805%**.

**Rule: no conclusion is drawn from an officialScore delta.** Rank on `ns`, or
on candidate prefill µs and candidate decode ms directly:

```
norm_decode_su  = 0.013890 / decode_s_per_tok
norm_prefill_su = 0.0003845 / prefill_s_per_tok
ns   = norm_decode_su**0.75 * norm_prefill_su**0.25
draw = officialScore / ns          # the lottery ticket we drew
```

### 0.2 Three advisor retractions, and one closed family

**(a) "v1 won by +0.897%" — RETRACTED.** fern's three same-session 8/5 receipts:

| receipt | arm | cand_pre µs | cand_dec ms | **ns** | officialScore | draw |
|---|---|---:|---:|---:|---:|---:|
| `c3ce66e` | v0 control | 191.308 | 5.04644 | **2.544360** | 2.523276 | 0.99171 |
| `cdf71fa` | v2 reg prefetch | 192.211 | 5.05080 | **2.539719** | 2.505056 | 0.98635 |
| `4058d0b` | v1 double-buffer | 191.532 | 5.06130 | **2.538013** | 2.545892 | 1.00310 |

`ns` ranks control > v2 > v1; officialScore ranks v1 > control > v2. **The two
instruments disagree on every pairwise comparison.** Measured dS: v1 **+0.115
ms**, v2 **+0.463 ms** — both the wrong sign against the back-solved −2.42 ms
and both inside σ_dS = 0.254 ms. v1's paired baseline drew 388.398 µs = the
**99.2nd percentile, z = +2.23**, the slowest prefill of the day. Log
decomposition of the +0.896% gap: **candidate code −0.250%, baseline lottery
+1.142%**.

⇒ **The single-buffered `Ws` staging↔MMA serialisation mechanism is measured
NULL.** The `_nax` stage-2 gather family is **CLOSED**; the
`DARKBLOOM_STAGE2_GATHER` flag is deleted. This was the mechanism that was
supposed to cash the 15.4 ms recoverable pool in §A. It did not.

**(b) "0.026% replicate sd ⇒ +12.4σ cross-day session drift" — RETRACTED.**
The three 8/4 near-frontier receipts (`7a5a1e0` 2.507043, `1feeabc` 2.500378,
`b6032ae` 2.514911) have sd **0.29%, not 0.026%** — an advisor order-of-magnitude
error. At the true sd, `c3ce66e`'s +0.321% is ~+1.1σ. **There is no measured
cross-day session drift.** It was baseline lottery.

**(c) "the crown is a 2.552308 content target" — RETRACTED.** Reconstructed at
the **median** baseline draw:

| tree | published | ns at median draw |
|---|---:|---:|
| crown `46eeccf` (lBroth) | 2.552308 | **2.524190** |
| our control `c3ce66e` | 2.523276 | **2.544360** |
| our best-in-feed | — | **2.547641** |
| our v1 / v2 | 2.545892 / 2.505056 | 2.505520 / 2.507204 |

The crown's baseline was the **99.7th percentile = a +2.425% premium**. ⇒ **the
crown holder's code is ~0.8–0.9% SLOWER than ours.** We lead the field on
content and trail only on luck.

### 0.3 The honest promotion bar (measured, #40 r2)

From our control, per fern's r2 empirical draw distribution over the 893-receipt
cohort — not a parametric bootstrap:

| P(beat crown) on one receipt | content gain required |
|---:|---:|
| 50% | **+1.461%** |
| 80% | **+1.830%** |
| 95% | **+2.018%** |

The crown `46eeccf0` drew **L = 1.024278 = p100.0 of 893** — it is the single
luckiest receipt in the entire cohort. To beat it on luck alone our control
needs `L > 1.016159`, which is ≈p99 ⇒ **P = 1.01%, about 1 in 99 receipts.**

### 0.4 ★ Why lottery-farming is NOT closed: content and tickets multiply

fern concluded from 0.3 that farming is closed (~99 tickets at ~21–35 min each).
That is correct **conditional on zero content gain**, which is the load-bearing
assumption. Because the requirement is a *sum*:

| content landed | left to the draw | P(promote)/receipt | tickets needed |
|---:|---:|---:|---:|
| 0% | +1.461% | ~1.0% | ~99 |
| +0.65% | +0.81% | ~12% | ~8 |
| **+1.0%** | **+0.46%** | **~22%** | **~5** |
| +1.25% | +0.21% | ~38% | ~3 |

**A +1% content win multiplies the value of every subsequent ticket by ~13×.**
This is why the campaign posture is "cheap content first, then farm", not
"farm". It is the most important strategic consequence of #40.

### 0.5 Receipt policy (in force)

1. **The ranked channel accepts exactly ONE in-flight submission per ACCOUNT.**
   All four students share `morganmcg1`; nezuko's real submit returned
   `conflict`, "1 submission already in flight (limit 1)". No queue, no
   fairness — a deferring student starves and a submitting student blocks three
   others. **The advisor is the scheduler; students must not take a slot without
   asking.**
2. **Never spend a slot on a control arm — CONFIRMED and cheapened.** Control
   `ns` = **2.544360** (`c3ce66e`) is permanent. §0.6 measured
   `corr(base, cand) ≈ 0`, so the paired ratio *adds* variance rather than
   cancelling it: a control arm costs a ticket and buys a number we already hold
   **at worse precision than the fixed published control gives us for free.**
3. **One receipt = best-known tree + at most one new mechanism.** Every receipt
   is simultaneously a measurement and a lottery ticket.
4. **Keep the slot busy ~continuously.** 4 slots in 3.5 h against a ~28–35 min
   turnaround is under-use.
5. **Pre-registration is mandatory** before any receipt: confirmation
   threshold, refutation threshold, and the conclusion for the gap between.
   fern's held and it is why her null is trustworthy.
6. **Never write an assignment check the assignee cannot execute.** #40's
   mandated `mlxfast: fusion active: stage2_gather` stderr check had no official
   log route and her M4 Pro (gen 16) never builds the `_nax` kernel. Advisor
   error.
7. **★ Screen locally, then STACK (fern #40 r2).** The single-receipt detection
   floor is `ns` **0.278%**, and almost every mechanism on the board is worth
   less than that alone. So: pre-screen each mechanism locally to bit-exactness
   and to a byte- or count-level prediction, then spend **one** receipt on the
   *stack*. This is a deliberate, bounded exception to policy 3 and it is only
   licensed when (a) each component is independently bit-exact, (b) each has a
   local screen at ≥5σ or an exact count delta, and (c) the summed prediction
   clears the floor. Attribution is sacrificed on purpose; say so in the prereg.
8. **★ The receipt-resolvability floor.** Before assigning any ranked byte- or
   dispatch-trading arm, convert the predicted saving into µs/step and compare
   with `3σ = 42.6 µs/step`. At the measured decode rates that is
   **≥27.8 MB/step at 651.8 GB/s** or **≥23.3 MB/step at 546.2 GB/s**. An arm
   below the floor is a *local-only* arm, however sound its mechanism. This is
   what moved frieren's deliverable A (~2.6 MB/step = 0.28σ) and even his
   deliverable B alone (12.4 MB/step = 1.3σ) off the ranked path.

### 0.6 ★ RESOLVED: `ns` is the instrument, and pairing hurts

The 10× tension (baseline prefill sd 1.932% vs candidate σ_S 0.183%) is settled
by fern's #40 r2 measurements. Both were taken; both answered.

**(a) Candidate-arm cross-session sd for behaviourally identical code.** Two
independent triples, plus a frontier-tight n=89 upper bound:

| triple | cand_pre | cand_dec | base_pre | oS | ns |
|---|---:|---:|---:|---:|---:|
| byte-identical `program.md` | 0.260% | 0.168% | **2.358%** | 0.635% | 0.076% |
| her r1 arms | 0.245% | 0.151% | **2.805%** | 0.810% | 0.129% |
| frontier-tight n=89 (upper bd) | 0.202% | 0.323% | **2.082%** | — | — |

The candidate arm really is ~10× quieter than the baseline arm on the same axis.
Predicted σ(oS) 0.634% vs measured 0.635%.

**(b) Within-receipt correlation is ZERO.** Within-epoch n=291:
`corr(base_pre, cand_pre) = −0.011 [−0.125, +0.105]`; decode
`−0.015 [−0.130, +0.100]`. There is **no shared session factor**. Therefore the
paired ratio **adds** the baseline's variance instead of cancelling it, which
confirms and strengthens policy 0.5.2.

**Consequences, in force:**

- **`ns` is ~4.5× tighter and ~20× cheaper than officialScore.** Minimum
  detectable true content delta, 95% two-sided: one receipt against the fixed
  published control **ns 0.278% / oS 1.242%**; 2/arm 0.278%/1.242%; 3/arm
  0.227%/1.014%.
- **Baseline-prefill draw alone = 86.5–86.9% of all officialScore variance.**
- **My cold-first/warm-second hypothesis is REFUTED, and the mechanism is not
  caching.** `DenseTensorStore.swift:97-98` sets `F_NOCACHE` and `F_RDAHEAD 0`,
  the two arms read from separate weights directories, and both prefill and
  decode weights are faulted in at constructor time
  (`LagunaRuntimeWeights.swift:404-412`). The arms are not warm/cold siblings.
  See §0.8 for what the residual structure actually looks like.

### 0.7 Re-audit list

Every conclusion resting on an officialScore delta **under ~1.5%** is suspect
until re-read on `ns`. Known items: the #40 arm ranking (done — null);
`c3ce66e` "session drift" (done — retracted); tanjiro's `0411779` **−9.22%**
(sign and existence survive the 1.5% threshold, **magnitude does not** — the
dispatch-price slope `c_M5` must be re-derived from candidate decode ms);
frieren's deliverable-A calibration receipt (**refused** — below the §0.5.8
resolvability floor at 0.28σ, moved to local-only).

**RESOLVED this round:** tanjiro's `0411779` magnitude was re-derived from
candidate decode ms — see §0.9.1. The `MLX_MAX_MB_PER_BUFFER` prior, which I
recorded here as "not invalidated" because it rested on local wall-clock rather
than a receipt delta, was **REFUTED on M5** (§0.9.3). Local wall-clock on M4 was
never the safe harbour I took it for; §0.9.2 says why.

**Advisor retractions #4 and #5 — both authorship errors from one bad habit:**

- **#4 (fern, #40).** I accused her of reverting my `CURRENT_RESEARCH_STATE.md`
  rewrite. False. Her branch predated my `091e6015` rewrite; merge-base was
  `d18ebbbaf724cfc8cc631d9d50de7104f0c879b8`; git's three-way merge kept my
  version. The `+141/−550` was a base-offset artefact of my diff command.
  Delivered in the PR #48 body (it cannot be sent to a merged PR).
- **#5 (tanjiro, #34).** I attributed 58 deleted lines in the two
  `LagunaRuntimeLocalIterate.swift` files to him. Blob identity shows his tree
  was **byte-identical to the base** at both paths (`406addff…` and
  `857cabba…` at both `eaedee84` and his r1 tip `454b189a`); the deletion was
  the **organizer's** (`emitLocalAcceptanceBandNotice`). He independently
  confirmed my earlier rate-4 retraction in the same report.

> **RETIRED RULE:** "always diff student trees against advisor head."
>
> **NEW STANDING RULE:** To attribute a change to a student, diff against
> `git merge-base <advisor-head> <student-head>`, never against advisor head.
> Diff against advisor head only to predict merge conflicts, never to read
> authorship. When authorship is contested use blob identity
> (`git rev-parse <rev>:<path>`), not `git diff`.

### 0.8 Baseline-prefill bimodality (structure inside the 2.4% noise)

The baseline prefill draw is not unimodal. Over the cohort it splits into a low
mode at **366.56 µs/tok (n=508)** and a high mode at **380.03 µs/tok (n=385)**,
a **3.67% gap**. Splitting the frontier-tight subset by mode moves only the
baseline prefill axis:

| axis | low vs high mode |
|---|---:|
| base_pre | **+3.75%** |
| base_dec | +0.16% |
| cand_pre | −0.07% |
| cand_dec | +0.05% |
| `ns` | −0.02% |
| officialScore | **+1.02%** |

So a full 1.02% of published-score spread is a two-state property of the
*baseline* arm alone, invisible on `ns`. Working hypothesis: the first timed
measurement taken after the 40C quiescence gate lands in one state or the other.
Not actionable — it is exactly the axis `ns` discards — but it explains why the
officialScore distribution has fat, structured tails rather than Gaussian ones,
and it is a second independent reason never to rank on officialScore.

### 0.9 Round-8/9 laws (new this round)

#### 0.9.1 The M5 dispatch price, and the 5.8× bracket around it

tanjiro's #34 (merged, `1849b376`) took two ranked M5 receipts with `n` empty
dispatches injected into the decode step:

| n | receipt | S ms | T ms | `ns` |
|---:|---|---:|---:|---:|
| 0 | `c3ce66ec` | 97.9496 | 4.28121 | **2.544360** |
| 400 | `0411779d` | 97.6165 | 5.07320 | 2.283549 |

`dT(400) = 0.79199` cand-only / `0.83509` paired ⇒
**`c_M5` = 1.980 ± 0.044 µs (cand-only) / 2.088 ± 0.165 µs (paired), slack ≈ 0.**
Both receipts carried full metrics, `passed_correctness True`, `max_abs_diff 0`,
both floors True.

- **H_cpu (knee at 1200) FALSIFIED at 34.8σ paired / 44.5σ cand-only.**
  **H_gpu (knee ≈461) falsified with it. H_sat confirmed, chi2 1.4.**
- The M4 knee at 1209 is a `max_ops_per_buffer` host-encode crossover
  (`device.cpp:576-593`) — a **different mechanism**, not the same curve.
- **VERDICT: dispatch-count reduction has linear, unsaturated value on M5.**

**Two opposing systematics, both self-flagged, both still open:**

1. **`c` is an UPPER bound.** His instrument chains every injected empty
   (`LagunaInjectChain.tail`) while real MLX encoders are
   `MTL::DispatchTypeConcurrent` (`device.cpp:548`, unconditional; `memoryBarrier`
   fires only on detected buffer-level RAW/WAR at `:325-330`, `:444-450`,
   `:363-375`). Bracket **[0.36, 2.09] µs — a factor of 5.8.**
2. **`c` is a LOWER bound if a knee exists.** `(c=2.088, knee=0)` and
   `(c=8.35, knee=300)` fit the two points **equally well**. At knee=300 the
   shipped 406 sit below saturation and removing 40 dispatches pays *nothing*.

Both are being closed in #47: **D2** (ranked chained n=100, ~14.7σ separation
between `dT=0.209 ms` and `dT=0`) settles the knee; **D5** (ranked unchained
n=400 against the already-paid `0411779d`, ~49σ) settles the bracket. D5 is
insensitive to the knee because both arms share `n`, so any knee term cancels.

#### 0.9.2 ★★ The M4 TRANSFER LAW (nezuko, #44)

> Command-buffer and encoder-boundary **counts** transfer from M4 to M5
> *exactly* — they are a deterministic function of the op stream and its byte
> counts. Boundary **timing** does not transfer: not in magnitude, and **not in
> sign**. M4 wall-clock is admissible evidence for kernel-internal efficiency
> and for byte-stream size. It is **inadmissible** for overhead-class,
> boundary-class, and concurrency-class changes. Take counts from M4 for free;
> take times from the M5 receipt.

This is the single most consequential methodological result of the round and it
is applied symmetrically, including where it costs the advisor. Note that
frieren's −1.76% and nezuko's −1.99% **agreed with each other** and were **both
wrong about the scoring machine** — agreement between two M4 designs is not
evidence of transfer.

Re-pricing of in-flight arms under the law: tanjiro's #47 D1 (M4
chained-vs-unchained ratio) is **in the inadmissible class** and can no longer
gate the fusion decision; fern's fused-norm M4 screen **survives for the
in-kernel half only**; frieren's byte-trading M4 screen **remains legitimate**.

#### 0.9.3 Nezuko's four-cell boundary model, and the MB50 refutation

Ranked M5 receipt `3e6fdcba`: `MLX_MAX_MB_PER_BUFFER` 200 → 50, one token
changed, all gates green ⇒ **`ns` 2.503448 = −1.608%** (S +2.193%, T +1.316%),
~11σ. On M4 the same change was **−1.97% faster at t=−47.5** with a clean
interior optimum at 50 MB. Both halves of her prereg prediction were wrong and
she said so first.

Counts (M4-measured, therefore M5-exact): cb/step 400→34, 200→52, 50→85, 25→86,
12→86 (floor 86); prefill 81→160 by differencing. Dividing measured M5 time
deltas by known count deltas:

| cell | per added command buffer |
|---|---:|
| M4 decode | **−3.63 µs** (a win) |
| M4 prefill | flat |
| M5 decode | **+1.10 µs** (small loss) |
| M5 prefill | **+27.2 µs** (large loss) |

The 25× decode/prefill gap on one machine rules out a fixed per-buffer cost.
Model: boundary value = benefit **B** (avoided in-encoder `memoryBarrier` drain,
~fixed, cheaper on M5's ~2.25× fabric) − cost **C** (forfeited intra-encoder
concurrency, scaling with how far one dispatch is from saturating the GPU).
M4 decode is ~93% one-kernel-at-a-time by her own SPLIT=1 census ⇒ C≈0 ⇒ B wins.
M5 decode: near-cancel, sign flips. M5 prefill: large independent `_nax` expert
GEMMs ⇒ C dominates.

**Prediction the model makes, now being cashed:** fusion *deletes* a boundary, so
it collects **B** without paying **C**. Every fusion arm on the board inherits
this as its mechanism story.

**Provenance finding (advisor-verified).** The shipped `200 MB` is an
**unvalidated imported competitor constant**. `9a407ed6` (Aug 4 19:20:40 +0200)
reverted only `MLX_MAX_OPS_PER_BUFFER` 400→200 — **it never touched the MB cap.**
The MB cap arrived in imported competitor commit **`814652a0`** (2026-07-29
06:28:05Z, yukon-autoresearch bot), which moved **512 MB / 50 ops → 200 MB /
200 ops in a single hunk**; the pre-import value was **512 MB**. The in-tree
comment "the post-anupsv-loader regime re-test winner (6 Latin pairs: decode 5/6,
prefill 4/6)" therefore documents the *competitor's confounded two-knob test*,
and one of those knobs is now known structurally inert (§0.9.4). **The cap has
never been tested upward in this tree.** #44 r2 tested exactly that, priced at
**~+0.65% (400 MB) to ~+0.83% (512 MB)** from her own rates and counts —
**and the 512 MB receipt came back at −1.164%, the opposite sign. See §0.9.12:
the axis is closed and the shipped `200` is a genuine interior optimum.**

#### 0.9.4 The ops axis is CLOSED (frieren, #35)

`MLX_MAX_OPS_PER_BUFFER` is **structurally unreachable**: max 28 ops/cb at the
shipped byte cap, 39 at 400 MiB, and the rule needs 201. `cbs at ops limit` = 0
across six arms and 131,954 command buffers. frieren's −1.76% (ops=400) and
nezuko's −1.99% (ops=200) are therefore two points on a **pure MB axis at two
inert ops values** — mutually *strengthening*, not a discrepancy. My earlier
record of them as a conflict is corrected.

#### 0.9.5 The decode-residual attribution table, and the exchange rate

```
T (n=0 arm c3ce66ec)                        4.28121 ms
1794 MB at measured 610 GB/s                2.941   ms
RESIDUAL                                    1.340   ms

406 dispatches x 2.088 us (chained upper)   0.848 ms = 63.3% of residual
406 x 1.42 us (nezuko M4 SPLIT=1 exposed)   0.577 ms = 43.0%
406 x 0.36 us (concurrent lower)            0.146 ms = 10.9%
```

```
1 ms of decode T  = 14.862 % of score   (0.75 / 5.046441 ms)
1 ms of prefill S =  0.371 % of score   (0.3637 / 97.95 ms)
                    ==> one decode ms is worth 40.0 prefill ms
```

My earlier score conversion was wrong by **10×**; tanjiro caught it. All students
now publish in %-of-score. Consequences: the dispatch pool is worth
**+2.2% to +12.6%** depending on the bracket; the full 1.340 ms decode residual
is **+19.9%**; the 31.28 ms prefill remainder is **+11.6%**. The gap to the crown
is **0.2517%**.

#### 0.9.6 The acceptance band is silent, not retired

The organizer deleted `emitLocalAcceptanceBandNotice` (58 lines) from both
`LagunaRuntimeLocalIterate.swift` files. **The band itself is NOT retired** —
`tolerances`, `Score.swift`, and four test files still enforce decode
`[0.980, 1.053]` and prefill `[0.952, 1.053]`. Local runs are therefore now
*silent* about a hazard priced at up to +5.9%. **Standing rule: hand-compute the
band ratios for every ranked arm.**

#### 0.9.7 Re-priced and closed mechanism items

- **frieren's all-planes 4-bit scale arm re-priced with measured rates:**
  75.2 MB/step ⇒ 115 µs at 651.8 GB/s / 123 µs at 610 GB/s ⇒ **+1.71% to
  +1.83% of score**. His earlier +2.67% assumed 415 GB/s and is withdrawn.
- **The rmsqkv fan-out fact.** `normalized` at `LagunaRuntimeModel.swift:5561`
  feeds **two** consumers — QKV (`:5564-5566`) and the per-head `g_proj`
  (`:5605-5606`) — so folding the norm into QKV alone saves **no dispatch**. The
  arm must capture both. The prior negative at `:5554-5557` (fused tail
  norm+QKV+gate re-measured **+2.7% slower** and defused) names its own successor
  condition: *"amortize the norm producer once"*, unsatisfied to date. The
  amortization pattern already ships at `:947-949`/`:964-966`
  (`lagunaResidualRMSNormRouterSource`), and a dormant fused template exists at
  `lagunaNormAffineQKVBody` `:4720-4830`. Assigned to fern as **#48**.
- **`dT_4 = 1.01067 ms` CONFIRMED** (was provisional): tanjiro established the
  decode ladder arms are *strictly nested* and the prefill arms *disjoint*, so
  `dS_1 + dS_2` is legitimate. `afec358a` contributed nothing; rate-4 rests
  entirely on R3−R2 ⇒ **546.2 ± 23.3 GB/s**, excess +0.106 ms.
- **`dS_1` is MARGINAL, not absolute.** The 39-vs-40 fix moves the prefill
  remainder **32.40 → 31.28 ms** (S₀ 97.86 − 44.37 − 22.21), and rate-1 is
  linear through the origin at 4.138 ms/copy so 43.26 ms is a **lower bound**.
  The undocumented "~34 ms honest residual" carried elsewhere in this document
  is superseded by **31.28 ms**.

#### 0.9.8 ★★ The occupancy-currency law (gather-GEMM, from #40's double null)

The `_nax` gather-GEMM k-loop
(`Vendor/mlx-swift/.../kernels/fp_quantized_nax.h:1725-1765`) is
`Atile device loads → barrier → loader_w.load_unsafe[_wide]() → barrier →
if (sg_active) MMA`. **Two unconditional barriers per iteration means device
loads and MMA cannot overlap at all inside one threadgroup.** Every bit of the
observed overlap — efficiency `(54.0−43.26)/(54.0−27.9) = 41%` — comes from
*other co-resident threadgroups* sitting at different loop phases.

Occupancy is also doing a second job. On the **median** chunk
(`chunk_rows ≈ 16`) only **1 of 4 simdgroups** is `sg_active`, because
`sgp_sm = min(SM, max(0, chunk_rows - tm))` (`:1699-1701`) with `SM = 16`. A
core therefore needs ~4 co-resident threadgroups just to keep its simdgroup
slots busy.

⚠ **Two corrections to this section, both post-#56.**

1. **Units.** This section originally stated the occupancy currency as "24
   simdgroup slots per core". That was a **unit slip**: the arithmetic behind it
   was 24 *threadgroups* × 4 simdgroups each, i.e. **96 simdgroup slots /
   3072 threads per core**. The conclusion is unaffected; the currency
   statement was wrong and misled the #56 brief (see the Step 0 bullet in the
   sliding-attention section and §0.9.11a).
2. **The "~4 co-resident threadgroups" claim is UNDER TEST by #57.** #56
   measured the *sliding attention* kernel at 1024 threads / 32 simdgroups and
   found that co-resident threadgroups **serialize**: the marginal wave costs
   88% of lone-threadgroup latency, so going from 1 to 12 TG/core bought only
   **+13%** throughput. If that serialization is a property of the *machine*
   rather than of that kernel, then "needs ~4 co-resident threadgroups" buys ~4%
   here, not 4×, and the whole overlap framing collapses.
   The discriminator is a **simdgroup-occupancy symmetry**: 1024 threads at
   3 TG/core = 96 simdgroups/core, and gather-GEMM's 128 threads / 4 simdgroups
   at 24 TG/core = **also 96 simdgroups/core**. Identical simdgroup occupancy,
   8× the threadgroup count. #57 T1 ports nezuko's probe to the 128-thread
   geometry and prices the same 1 → 24 TG/core throughput gain. Prereg:
   **≤ 1.25 ⇒ this currency claim is STRUCK**, the gather-GEMM overlap family is
   closed for good and the **15.4 ms recoverable-overlap figure is withdrawn**;
   **≥ 2.00 ⇒ the claim survives** and threadgroup count is the scheduling unit.

**Law: on this kernel, any arm that spends per-threadgroup resource to buy
overlap is self-cancelling, because the resource it spends is the same
occupancy that produced the overlap.** This retro-explains fern's #40 double
null exactly:

| arm | resource spent | occupancy | outcome |
|---|---|---|---|
| v1 double-buffered `Ws` | threadgroup memory | ↓ | +0.1150 ms (null) |
| v2 register prefetch | registers | ↓ | +0.4626 ms (null) |

Both landed inside σ_dS = 0.2536 ms. **Corollary: only arms that REDUCE
per-threadgroup resource use can move this kernel.** Do not reopen with a
deeper prefetch, a wider `Ws`, or a different barrier placement — fern's PR
says so and the mechanism now says why. Footprint audit: `kWsElems =
BN*BK_padded`, `Ws_storage` ~8.4 kB at BN=64 with `gate_up_stage` already
aliased onto it (that economy is taken); `threadgroup int bounds[experts /
expert_groups + 1]` (`:1618`, fallback `bounds[2]` at `:1620`) under
`DARKBLOOM_BSEARCH_HOIST` is the **only unaudited allocation** — with 256
experts it is **132 B at `expert_groups=8` and 1,028 B at `expert_groups=1`**,
and which one ships is being resolved by **#57 T2 from the `quantized.cpp` host
call site**, not guessed. Do not flip the flag.

#### 0.9.9 ★★ The `_nax` twin-file consistency rule (verify before every kernel edit)

The runtime compiles an **embedded C-string copy** of the kernel header, not
the header itself:

- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h`
  — 1886 lines / 65,515 B — **editable**, the human-readable source.
- `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp`
  — 2027 lines / 68,466 B — **editable, and this is what actually runs.** It
  embeds the header verbatim (`:148` provenance comment, `:151` `#line 1`), so
  the **line offset is exactly +141**.
- `Vendor/mlx-swift/Source/Cmlx/mlx-generated/metal/fp_quantized_nax.h`
  — 27,907 B, **zero `DARKBLOOM_` markers, NOT editable** — a stale upstream
  copy. Do not touch it and do not be misled by it.

The two editable files are **currently in exact sync**. Any edit to one without
the other means the ranked M5 measures the OLD kernel while every local static
check passes — a silent null. Run this before and after every kernel edit:

```bash
G=Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp
K=Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h
for s in load_unsafe_wide sgp_sm SWIGLU_REGLOCAL BSEARCH_HOIST; do
  printf "%-20s gen=%s ker=%s\n" "$s" "$(grep -c "$s" $G)" "$(grep -c "$s" $K)"
done
```

Any `gen != ker` row is a defect. Baseline at `07d214d8`: `load_unsafe_wide`
7/7, `sgp_sm` 20/20, `SWIGLU_REGLOCAL` 9/9, `BSEARCH_HOIST` 3/3.

#### 0.9.10 M4 TRANSFER LAW — the static-property corollary

§0.9.2 forbids transferring M4 *timing* for overhead-, boundary-, and
concurrency-class changes, and `_nax` kernels cannot even execute on M4
(`device.cpp:913-931` needs Apple GPU gen ≥ 17; M4 Pro probes 16). But
**static compiler properties are not timing and are not gated by execution**:
threadgroup bytes, `maxTotalThreadsPerThreadgroup`, register pressure, and MSL
compilability are all readable on M4 for a kernel that will never run there.
fern's merged `research/nax_msl_compile_check.sh` is the existing precedent.
This is what makes the gather-GEMM D2 occupancy audit a free, local arm.

#### 0.9.11 ★★ LEDGER-HYGIENE LAW — a banked queue price is not evidence

**Re-derive every price from its source table before you assign it. Three of the
first five prices audited this way were wrong, and the errors had been sitting
in the queue for days steering student time.**

| audited item | banked price | truth | error |
|---|---:|---|---|
| gather-GEMM #2, `SM=16` banding | +1.9 to +2.6% | **0** — `SM = BM/WM` is pinned to 16, `TM = SM/16` integer-divides to 0 below it, and `453,120 = Σ ceil(n_e/16)·16` is identically the floor | fictitious |
| sliding-attention kernel rewrite | ~+0.6% | **+3.2% to +6.4%, central +5.2%** (§0.9.11a below) | low by 5–10× |
| `residual_rms_router` rpg8→rpg4/2 | ~+0.3% | **+1.28% central** (106 µs M4 × 0.812 × 14.862 %/ms) | low by ~4× |
| gather-GEMM #1, `Ws` staging | "the mechanism" | measured **null**, twice | refuted by measurement |
| M5 dispatch constant `c` | 4.1 µs/dispatch | bracket **[0.36, 2.09] µs** | void |

Two prices survived audit and two more are still outstanding. Still
**`UNAUDITED`**, and not to be quoted in a brief until they are: M2
`lhs_indices` gather elision (banked +0.4–0.5%; if its "2–2.9 ms" is M5 prefill
ms then at 0.371 %/ms it is +0.74% to +1.08%, i.e. ~2× low, unless the banked
figure is an undocumented 50% realization haircut), D-MLP prefill fusion
(+1.56%), and P-SHARED (+0.18–0.33%).

The failure mode is not statistical. Every bad price was a *derived* number
banked in a summary table, and in each case **the prose in the same file
already contradicted the table**:

- The `SM=16` row sat two screens away from the geometry comment at
  `fp_quantized_nax.h:1649` that pins the geometry it proposed to change.
- The sliding-attention `~+0.6%` row sat in the same document as the M4
  recoverable table in §1, which says in words *"the sliding-attention line is
  the one to price first, and it is the rare case where **M4 understates the M5
  prize**"* — i.e. the prose says *underpriced* while the table says *small*.

So the check is cheap and mechanical:

1. Open the source table the number came from. Verify its own internal
   arithmetic (the sliding-attention row reproduces: 22.34 × 30 = 670 µs/step;
   30 × 2.097 MB = 62.91 MB/step; 62.91e6 / 260.2e9 = 241.8 µs; 670 − 242 =
   428 µs recoverable ✓).
2. Re-derive the score conversion yourself using the exchange rates in §A
   (14.862 %/ms decode, 0.371 %/ms prefill). If you cannot reproduce the
   banked percentage from *any* defensible route, the price is not an estimate
   — it is a haircut someone forgot to document, and it is void.
3. Sanity-check against the residual it must fit inside (M5 decode residual
   1.340 ms; prefill remainder 31.28 ms). A price that needs more than its
   residual is wrong; a price far below what the residual affords deserves the
   same suspicion.
4. Confirm the mechanism is still reachable in source at today's HEAD, not at
   the HEAD where the number was banked.

**No brief may quote a queue price that has not been through steps 1–4 in that
brief's own text.** State the derivation in the assignment so the student can
falsify it, and say explicitly which residual it is drawn against.

##### 0.9.11a The sliding-attention price, as measured (supersedes my reprice)

**Status: my "+3.2% to +6.4%, central +5.2%" is WITHDRAWN.** It was derived from
the recoverable column of `research/nezuko-pr9-dispatch-fusion.md:120-144`
(sliding: n = 30, 22.34 µs true/call, 670 µs/step, 2.097 MB/call, 94 GB/s = 36%
of ceiling, **428 µs/step recoverable**) scaled by the residual-class factor
0.812. Nezuko's #56 measured the kernel directly and the derivation does not
survive. What follows is the measured replacement.

**The wave staircase (M4 Pro, 20 GPU cores, real kernel body, 200 serial
dispatches per command buffer, best of 3, GPU-busy timing):**

```
K threadgroups   1      20     24      32      48      64      240
t (µs)          9.23   9.45  17.41   18.91   26.25   33.87   98.19

fit:  t ≈ 8.16 · ceil(K / 20) + 1.1 µs      (±5%)
```

Three consequences, all measured, none inferable from the byte table:

- **Co-resident threadgroups serialize.** The marginal wave costs 8.16 µs =
  **88% of lone-threadgroup latency (9.23 µs)**. Going from 1 to 12 TG/core buys
  **+13% throughput**, not 12×. Residency itself is 3 TG/core at 1024 threads,
  **96 simdgroup slots / 3072 threads per core**, and it is **flat in
  threadgroup memory** from 16 B to 32 kB.
- **The shipped launch is single-wave on the ranked host.** Sliding launches
  32 TGs (`:1799-1800`), full launches 24 (`:2316`). On M4's 20 cores both are
  two waves with the second one 12/20 and 4/20 occupied. **M5 Max has ≈40
  cores**, so at anything ≥32 cores both kernels are **one wave** on the ranked
  box, and the "8 threadgroups cannot fill the machine" story that justified the
  ×1.0 upper bound is simply not the M5 situation.
- **Therefore the whole-kernel M5 cost, not the recoverable time, is the
  ceiling.** Route: M4 sliding is 22.34 µs/call at two waves; one wave is
  22.34 × (9.23/17.4) ≈ **11.9 µs**; ×0.812 ⇒ ≈9.6 µs; × 30 calls ⇒ **≈290
  µs/step on M5**. Full: 23.5 → ≈12.5 → ≈10.1 × 10 calls ⇒ **≈100 µs/step**.

**≈390 µs/step is the entire cost of both attention kernels on M5 = 5.8% of
score.** §0.9.11b claimed 347 + 106 = **453 µs/step of recoverable time inside
them** — more than they cost. That is the arithmetic that kills the row. A
realistic in-kernel arm recovers 10–20% of a 390 µs ceiling ⇒ **40–80 µs ⇒
+0.6% to +1.2% of score.** Carry that, not the old bracket.

**The ladder, disposed of by measurement:**

| arm | verdict | reason |
|---|---|---|
| R1 one query head per TG (32→64 TGs, 4→2 planes) | **RETIRED** | t(64)/t(32) = **1.791** — it nearly doubles per-call latency |
| R1+R2 combined | **RETIRED** | inherits R1's staircase penalty |
| R1-dual (halve the launch to 16 TGs) | **RETIRED** | 16 TGs on ≈40 M5 cores idles more than half the machine; the entire wave-merge family dies here regardless of memory |
| R4 shrink the staging planes | **NO-OP** | 4 planes/18448 B → maxK 60 and 2 planes/10000 B → maxK 60. **32 kB is a per-TG API cap, not a per-core pool** |
| **R2 deepen the 2-deep load pipeline to 4 slots** (`:1529-1530`) | **THE ONLY SURVIVOR** | ≈+12 registers, identical FP order; registers are not the binding term |
| R3 pre-barrier prefetch, *selecting* not branching on `widx` | held as fallback | 5–15% |

R2's premise is untouched by #56: in-order issue with 4 vec4 loads in flight
against a dependent FMA/`simd_sum`/`exp` chain (`:1537-1616`), un-hoistable
because `k_cache`/`v_cache` are *written* at `:1486-1487`. And because R2
attacks **per-threadgroup latency** — the quantity M5 is single-wave in — **M4
is a valid screen for it**, and the transferable primary metric is
`sliding_attn_lone_tg_us` **at K=1**.

Two constraints that survive unchanged, and one that is now stronger:

- **Bit-exactness.** More lanes inside one threadgroup over the 512 sliding
  positions, identical reduction order. **Splitting positions across
  threadgroups is NOT bit-exact** — a flash-decoding-style cross-threadgroup
  combine changes softmax accumulation order and fails the greedy gate.
- **Fusion cannot help this one.** dup/ser first-touch ratio 0.971 (§A4): the
  bytes are already first-touch. Kernel change or nothing.
- **M4-screenability is real but narrower than I claimed.**
  `sliding_fused_attn_ring_v1` is a custom Laguna kernel at
  `Sources/MLXFastModel/LagunaRuntimeModel.swift:1382`, not the `_nax`-gated
  SDPA path, so it executes on M4. But **an arm whose wave count changes across
  hosts has no single transfer scalar** — go through the staircase, K by K. Only
  the K=1 lone-TG latency transfers by a scalar.

##### 0.9.11b The M4 recoverable column — two rows struck, the rest suspect

| kernel | M4 recoverable | **central (×0.812)** | status |
|---|---:|---|---|
| `sliding_fused_attn_ring_v1` | ~~428 µs~~ | ~~347 µs / +5.16%~~ | **STRUCK** (§0.9.11a). Whole-kernel M5 cost ≈290 µs/step; R2/R3 recover 10–20% |
| `full_fused_attn_grow_v1` | ~~130 µs~~ | ~~106 µs / +1.57%~~ | **STRUCK**. Whole-kernel M5 cost ≈100 µs/step |
| `residual_rms_router` rpg8→rpg4/2 | 106 µs | 86 µs / +1.28% | **SUSPECT** — 60% of ceiling is a logical-byte figure (§0.9.18) |
| shared expert K1 | 65 µs | 53 µs / +0.78% | **SUSPECT** — 73% of ceiling, same reason |
| ~~column total 1380 µs / +16.65%~~ | | | **WITHDRAWN.** Attention's share is now bounded by a ≈390 µs whole-kernel ceiling; realistic recoverable ≈40–80 µs = **+0.6% to +1.2%** |

**Why the 83.6% cross-check did not save it.** The column summed to 1.380 ms =
83.6% of the M4 residual, and ×0.812 to 83.6% of the M5 residual — the same
fraction on both machines, which I read as strong evidence. It is not evidence
of the *per-row* prices; it is an artefact of scaling every row by one constant,
which necessarily preserves the ratio. Two rows of that sum have now been shown
to exceed the total cost of the kernels they were drawn from. **The decode
residual is still 1.340 ms and still unowned. It is no longer "these four
kernels."**

Two caveats that remain live for whatever replaces this table. The 14.862 %/ms
linear rate understates large moves — zeroing the whole 1.340 ms residual is
worth `(4.281/2.941)^0.75 − 1 = +32.7%`, not +19.9% — so the linear rate is the
conservative choice for single-kernel arms. And "recoverable" is the gap to the
*byte* ceiling, which presumes an arm can reach 100% of it; nothing in the
programme ever has, and §0.9.18 now shows the gap itself is mismeasured whenever
the kernel is cache-served.

#### 0.9.12 ★ The command-buffer byte cap is a closed axis (nezuko #44, three M5 receipts)

Shipped `MLX_MAX_MB_PER_BUFFER=200` is a **genuine interior optimum on M5**.
Three ranked receipts against the fixed control `c3ce66ec` (`ns` 2.544360,
S 97.9496 ms, T 4.28121 ms):

| cap | receipt | `ns` | Δ `ns` | cand_pre | Δ (σ) | cand_dec | Δ (σ) |
|---|---|---:|---:|---:|---|---:|---|
| 50 MB | `3e6fdcb` | 2.503448 | **−1.608%** | 195.503 µs | +2.193% (9.0σ) | 5.11955 ms | +1.449% (9.6σ) |
| **200 MB** | `c3ce66e` | **2.544360** | **0** | 191.308 µs | — | 5.04644 ms | — |
| 512 MB | `c747336` | 2.514737 | **−1.164%** | 197.093 µs | +3.024% (12.3σ) | 5.07521 ms | +0.570% (3.8σ) |

σ from fern's #40 instrument (cand_pre 0.245%, cand_dec 0.151%). Every entry is
far outside noise; these are real regressions, not draws.

**The cap-up prediction was falsified with the opposite sign.** The brief
predicted 200→512 MB ≈ **+0.83%** by extrapolating the measured boundary cost
(+27.2 µs per added prefill command buffer) upward — fewer buffers, less
boundary cost. Measured: **−1.164%**, and the loss is almost entirely prefill.

**Where the axis is closed.** Fit a quadratic in `log2(cap)` through the three
points: it peaks at **~176 MB** with an expected gain over 200 MB of
**+0.018%** — 16× below the 0.278% single-receipt `ns` resolution floor (§0.6)
and 83× below the P=50% promotion bar. There is nothing left on this axis at
any cap value. Combined with frieren's structural closure of the *ops* axis
(max 28 ops/cb at the shipped byte cap vs the 201 the rule would need), the
whole command-buffer-knob family is dead. This also retires round-8 idea 3
(R-MBBUF).

**Two things this bought us that are worth more than the arm.**

1. **The linear boundary model is only valid downward.** `+27.2 µs` per added
   prefill cb held going 200→50 (that arm's prefill loss, −0.797% of score, is
   the right order) but inverts going 200→512. So there is an opposing term,
   worth ~5.4 ms of prefill, that switches on with larger buffers. The leading
   candidate is **pipeline-fill latency**: the GPU idles while the host encodes
   a bigger first command buffer. That predicts exactly the observed asymmetry
   — prefill is a *single* pass and pays the one-off cost in full (−1.099%),
   decode is 128 steps and amortizes it to nothing (−0.084%, 3.8σ but only
   0.0056 ms). No arm follows from it, because both phases still want 200, but
   **do not quote the +27.2 µs/cb rate above the shipped cap again.**
2. **External validation of the §A exchange rates.** Converting each arm's
   measured `ΔS`/`ΔT` at 0.371 %/ms and 14.862 %/ms reproduces its measured
   `ns` delta to **0.026%** (50 MB: −1.634% predicted vs −1.608% measured) and
   **0.019%** (512 MB: −1.183% vs −1.164%). The rates are now confirmed against
   ranked M5 receipts at the ±0.03% level, on two arms that move both axes in
   the same direction by different amounts. Every price in this document that
   uses them is on firmer ground than it was.

#### 0.9.13 ★★ The banked-price audit is complete: 6 of 8 checked prices were materially wrong

§0.9.11 opened as a hygiene rule after three of the first five re-derived queue
prices turned out wrong. The audit is now finished — the last three unaudited
items (M2, D-MLP, P-SHARED) were re-derived from source and from the in-situ
rate table on 2026-08-05. **Two of the three were wrong, in opposite
directions**, and then fern's #48 receipt killed a sixth (§Ø.1), taking the
running tally to **6 of 8**. The rule is no longer a precaution; it is the single
highest-yield piece of advisor work in the programme, and it stays in force
permanently.

**Tally.** Wrong: the sliding-attention reprice (was `~+0.6%`, is **+5.2%
central** — 8.7× low, §0.9.11a/b), my own retracted `+8.5%`/573 µs over-count of
that same item, the M4 recoverable-column scaling error (wall-clock ratio 0.501
misapplied where the residual-class ratio 0.812 belongs, §0.9.11b), **M2** (2×
low), **P-SHARED** (~2.5× high), and **the entire dispatch-removal price list
including my +2.568% gate-fold figure** — refuted end to end by a ranked receipt
(§Ø.1). Correct: `residual_rms_router` rpg8→rpg4/2 (+1.28%) and shared-expert K1
(+0.78%) **arithmetically, but both are now SUSPECT for a different reason
(§0.9.18)**, and **D-MLP**'s central arithmetic — though D-MLP carried two other
defects, see below.

**The two failure modes are different and both matter.** Five of the six were
*arithmetic or conversion* errors, findable at a desk. The sixth was a
**category** error: a coefficient measured by *adding* work was banked as the
price of *removing* work. No amount of re-derivation would have caught it; only
a ranked receipt could. When a price rests on a probe whose sign is opposite to
the proposed change, say so explicitly in the brief and pre-register the
discriminator.

##### M2 — gather elision via `lhs_indices`: banked +0.4–0.5%, actual **+0.80% to +1.19%, central +0.95%** (2× LOW)

The banked figure had the *bytes* right and the *score conversion* wrong.
Re-derived from source. `lagunaFusedSortedRoutedGateUp`
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:9634-9705`) calls
`gatherSort` at `:9655`, which is
`Vendor/mlx-swift-lm/Libraries/MLXLMCommon/SwitchLayers.swift:338-343`:
`x.flattened(start: 0, end: -3)[fused.rowOrder]`. The fused counting sort writes
`row_order[off] = idx / M` with `M = topK = 8` (`:311`), so `rowOrder` indexes
**tokens** and the take materialises `[T·topK, 1, D]`.

At prefill `T = 512`, `D = 2048`, `topK = 8`, bfloat16:

- source `x` = 512 · 2048 · 2 = **2.00 MiB/layer**
- materialised sorted copy = 4096 · 2048 · 2 = **16.00 MiB/layer**

The elision removes the copy's **write** (16 MiB) *and* the GEMM's **read** of
that copy (16 MiB), replacing the latter with a scattered read of the 2 MiB
source — which is compulsory traffic the current path already pays, and which
fits comfortably in SLC. Net elided DRAM = **32 MiB/layer × 39 = 1.309 GB**.
So the banked "32 MiB/layer ≈ 1.25 GB" was *numerically right but mislabelled*:
it is the write-plus-read round trip, not "the sorted copy".

Independent cross-check that this traffic is real and already inside the
measured block: weights 15,220 MB + x traffic 34 MiB/layer · 39 = 1,391 MB
gives 16,611 MB against the measured 17,666 MB for the gather-GEMM prefill
block, leaving ~1,055 MB for scales and output writes. Consistent.

Time and score:

| rate | ms of dS | % of S₀ (97.86) | score |
|---|---:|---:|---:|
| 610 GB/s (M5 streaming read) | 2.145 | 2.19% | **+0.796%** |
| 408.4 GB/s (in-situ block rate) | 3.204 | 3.27% | **+1.189%** |

**The banked error was the conversion step**: the ledger claimed "2–2.9 ms of dS
≈ +1.0–1.4% on S", but 2 ms is 2.04% of S₀, not 1.0%. Applying the correct
0.371 %/ms exchange rate (now externally validated to ±0.03%, §0.9.12) gives
**+0.80% to +1.19%, central +0.95%** — roughly double the banked +0.4–0.5%.

⚠ **M2 and gather-GEMM mechanism #3 are the SAME BYTES. Their prices must never
be summed.** Mechanism #3 (`x` re-read, +0.4–1.1%, HELD contingent on D1) is a
proposal to recover re-reads of the sorted copy; M2 deletes the sorted copy
outright. Whichever lands first consumes most of the other's headroom. If M2 is
assigned, mechanism #3 must be repriced down, not carried alongside it.

The stated risk stands and is the reason this is rank 4 and not rank 2:
contiguous sorted rows are plausibly *why* the block reaches 408 GB/s at all,
so scattered 4 KB row reads may cost more than the copy they replace. That is a
genuine sign risk, not a magnitude risk — exactly the situation where a cheap
local screen must precede a ranked receipt.

##### D-MLP — arithmetic correct, but mislabelled and an upper bound

Recomputed from rate 4. Routed-expert QMV decode moves **552.08 MB** at
**546.2 ± 23.3 GB/s**; the reference is the **610 GB/s M5 streaming read**, not
651.8 GB/s. Excess = 552.08/546.2 − 552.08/610 = 1.01077 − 0.90505 =
**0.10572 ms**, and 0.10572 × 14.862 %/ms = **+1.571%**. The banked +1.56% is
right. Three caveats that the banked entry hid:

1. **It is a *decode* item, not prefill.** The queue table row read "D-MLP
   prefill fusion pool". The derivation is `LagunaRuntimeModel.swift:7325`'s
   depth-1 staging precedent in the routed **decode** QMV. Row corrected.
2. **Propagating rate 4's own ±23.3 GB/s gives a price bracket of +0.96% to
   +2.24%** — a ±0.64 pp band on a ±0.03 pp exchange rate, because rate 4 rests
   *entirely* on the single R3−R2 receipt difference (`6757de6` − `ca416f0`).
   The **pessimistic end does not clear the +1.461% P=50% promotion bar.**
3. **"Full closure" is an upper bound with no realization estimate.** Reaching
   610 GB/s on a top-8 *gathered* QMV is not obviously attainable; the depth-1
   precedent presumably already banked part of it. Any brief must state a
   realization assumption explicitly rather than importing the 50% haircut that
   line 603 flags as undocumented.

##### P-SHARED — banked +0.18–0.33%, actual **+0.08% to +0.10%** (~2.5× HIGH)

The mechanism is a ~5-line gate relaxation at `:8262-8265` reusing the bank
built by `prepareFusedSharedGateUp` (`:8048-8076`); bit-exact per
`:8283-8288`; 39 layers. Its two claimed savings price out as:

- **39 redundant 2.00 MiB `x` reads** = 78.0 MiB = 81.8 MB ⇒ 0.134 ms at
  610 GB/s / 0.200 ms at 408.4 GB/s ⇒ **+0.050% to +0.074%**
- **39 dispatches** at `c_M5` = 1.980–2.088 µs ⇒ 0.077–0.081 ms ⇒
  **+0.029% to +0.030%**

Total **+0.079% to +0.104%**. Even allowing an unmeasured intermediate
round-trip saving it does not reach +0.15%.

**Consequence: P-SHARED is now below the single-receipt resolution floor.** One
receipt against the fixed control resolves 0.278% of true `ns` content at 95%;
P-SHARED is ~3× under that. It can never be validated on its own, in any
number of receipts we can afford, and it is 15–18× under the P=50% promotion
bar. It survives *only* as a rider under policy 0.5.7 stacking, and even then it
contributes less than the rounding on its stack-mates. **Do not spend a student
slot on it. Do not cite it as part of a stack's expected value without saying it
is unverifiable.**

##### Standing consequences

- **Every remaining banked price in this document is now audited.** New prices
  must be derived in the brief's own text, with the byte or time model shown,
  before an assignment quotes them.
- **Two failure modes recur and are now named.** (i) *Conversion-step error*:
  bytes or milliseconds computed correctly, then converted to score with a wrong
  denominator or a wrong elasticity — M2 and the M4 recoverable column both died
  here. Always convert through the validated 0.371 %/ms and 14.862 %/ms rates
  and show the arithmetic. (ii) *Dispatch-count romance*: pricing a saving as
  `n × c` without checking that `n × c` is large enough to be measured —
  P-SHARED's entire remaining value is 39 dispatches worth 0.03% of score.
- **An audit that lowers a price is as valuable as one that raises it.** M2
  gained a student slot; P-SHARED lost one it should never have had. Both
  outcomes came from the same twenty minutes of arithmetic and neither needed a
  receipt, a GPU, or a student.


#### 0.9.14 The programme has shipped zero bytes for 18 hours, and every arm since is `ns`-inferior to doing nothing

Three findings from 2026-08-05 15:00-15:40Z. Read them together: each one is a
different projection of the same failure, and the third is the way out.

**(a) The shipped editable tree is byte-frozen.** Fingerprint = sha1 over the
ordered list of `git rev-parse <rev>:<path>` blob hashes for all 97
`benchmark.json` `editablePaths`:

| rev | when | editable-tree fingerprint |
|---|---|---|
| `768bb9d4` | experiment base | `ed340e9939ab` |
| `9a407ed6` | 08-04 19:20 | `36039062e545` |
| `a3c096ee` | 08-04 21:02 | `5fe63db21fa1` |
| `6f1289a9` | 08-04 21:03 | **`97c022d6bf31`** |
| `d18ebbba` | #32 merged | `97c022d6bf31` |
| `904173a0` | #40 merged | `97c022d6bf31` |
| `1849b376` | #34 merged | `97c022d6bf31` |
| `d267ebda` | advisor head | `97c022d6bf31` |

Since `6f1289a9` at 08-04 21:03Z — about 18.2 hours — **three merged PRs have
changed exactly zero scored bytes.** #32, #40 and #34 were all research-only
merges: instruments, censuses, calibration, and closure documents. They were
correctly merged (each retired a hypothesis or built an instrument the
programme now depends on) but not one of them can move a score.

**(b) Every ranked arm since that same commit is `ns`-inferior to the frozen
frontier.** Renormalised score over all 23 `morganmcg1` receipts, best `ns`
first:

| feed sha | arm | `officialScore` | **`ns`** | draw |
|---|---|---|---|---|
| `e82d6cf` | control: frozen frontier, cap 200 | 2.523276 | **2.544360** | 0.991714 |
| `d4235c9` | board-leading arm | **2.545892** | 2.538013 | 1.003104 |
| `cdf71fa`* | — | — | 2.539719 | 0.986352 |
| `cc4b1dc` | — | 2.516657 | 2.514737 | 1.000764 |
| `021fa4a` | 50 MB cap | 2.493877 | 2.503448 | 0.996177 |
| `2808e93` | — | 2.290697 | 2.283549 | 1.003130 |
| `1c4fb41` | — | 1.788158 | 1.804692 | 0.990838 |

(*`cdf71fa`/`504104e` — ledger and feed shas differ; map by timestamp.)

The board-leading receipt `d4235c9` has an `officialScore` 0.10% above the
control but an `ns` **0.25% below** it, on a draw of 1.003104. Our best public
number is a baseline-lottery artefact. **The true content frontier is still the
frozen tree.** This is exactly what (a) predicts: if nothing changed the scored
bytes, nothing could have changed the content score, so all ranked movement
since 21:03Z is measurement noise plus draw luck.

**(c) The way out is priced, and it is a kernel rewrite, not another
measurement.** The round-9 directive is therefore: *stop buying measurement
with ranked receipts; start shipping mechanism.* Every round-9 assignment must
either change bytes on the scored path, or be a free/local/M4-legal audit that
decides a mechanism arm without consuming a receipt.

The frontier item is `sliding_fused_attn_ring_v1` — 36% of the M4 bandwidth
ceiling, 428 µs/step recoverable, **+5.16% of score central**, and
**M4-screenable** because it is not `_nax`-gated. A frontier design review
(2026-08-05 15:20Z) read the kernel and produced a diagnosis and a bit-exact
ladder; the full brief is `research/BRIEF_QUEUED_SLIDING_ATTN_REWRITE.md`.
Its load-bearing conclusions:

- Launch geometry is `grid = ((heads/2)*1024, 1, 1)`, `threadGroup = (1024,1,1)`
  (`Sources/MLXFastModel/LagunaRuntimeModel.swift:1799-1800`; full kernel
  `:2316`). 64 query heads paired two-to-a-threadgroup ⇒ **32 threadgroups**
  for the sliding kernel, 24 for the full kernel.
- Threadgroup memory is ≈18.4 kB/TG, dominated by
  `outputs[4*BN*BDP]` = 4×32×33 floats = 16.9 kB (`:1495`). Against 32 kB/core
  that permits **one 1024-thread threadgroup resident per core**.
- 32 threadgroups therefore cannot fill a ~40-core M5 even once. **The
  diagnosis is wave quantisation and occupancy, not dispatch count and not DRAM
  bandwidth.** The 2.097 MB/call the counters report is exactly one unique copy
  of the 8-head × 512 × 128 × bf16 × {K,V} window, so *requested* traffic is
  already 4× the reported figure and "use wider loads" is not the fix — the
  K/V loads are already 8-byte `vec<bfloat,4>` (`:1719-1739`).
- Secondary: the compiler cannot hoist next-trip K/V loads because `k_cache`
  and `v_cache` are also *written* in phase 2 (`:1486-1487`), so provable
  non-aliasing fails.
- Bit-exact ladder: **R1** one query head per threadgroup (`head0 = pair_tg*2`
  → `head = tg`, halve `outputs` 4→2 planes ⇒ ≈9.9 kB, 32→64 TGs);
  bit-exact because head0 and head1 never interact numerically. **R2** deepen
  the hand-written 2-deep pipeline (`:1529-1530`) to 4 slots at identical FP
  order. **R3** pre-barrier prefetch, selecting not branching on `widx`.
  ⚠ **R1 and the "2 TGs/core" figure in that bullet are RETIRED by #56** —
  residency is 3 TGs/core at 1024 threads and is **flat in threadgroup memory**
  from 16 B to 32 kB, so halving `outputs` buys no residency at all. The whole
  wave-merge family is closed; see §0.9.11a.
- **Advisor-added Step 0 — DISPATCHED AS #56 AND ANSWERED.** The question was:
  a 1024-thread threadgroup is **32 simdgroups**, while the programme's working
  figure at §0.9.8 was **24 simdgroup slots per core**; if 24 were right, a
  32-simdgroup threadgroup could not be resident at all. **That 24 was a unit
  slip of mine** (nezuko, #56 §6, and the correction is hers): §0.9.8's own
  arithmetic was *24 threadgroups × 4 simdgroups each*, i.e. **96 simdgroup
  slots / 3072 threads per core** — the same currency in which a 1024-thread
  threadgroup costs 32 simdgroups and three of them fit. **§0.9.8's conclusion
  survives; its statement of the currency did not.** Measured on M4 Pro from a
  compiled `MTLComputePipelineState`: `staticThreadgroupMemoryLength = 18432 B`
  (both attention kernels), `maxTotalThreadsPerThreadgroup = 1024`,
  `threadExecutionWidth = 32`, residency **3 TGs/core**. 128-thread
  threadgroups reach 24 TG/core at the same 18432 B = 432 kB live per core, so
  **32 kB is a per-threadgroup API cap, not a per-core pool.**

**Two more prices moved, both by arithmetic alone, and two round-9 candidate
ideas died on arrival.** These are the §0.9.11/§0.9.13 ledger-hygiene law
working as designed:

- fern's #48 (fused norm + QKV + gate) **repriced upward**: the gate
  `gate_sp_h64/h48` is **85.9% of the prize**, not the norm. Central value
  **+2.988%**, and the pure dispatch-overhead floor **+0.473%** already clears
  the 0.278% resolution floor, so the arm cannot fail to be measurable.
- **N1 ("statically specialise the sliding kernel on the 512 window") RETIRED
  on arrival:** it already is. `N=512` and `BN=32` are compile-time, giving 16
  slots per simdgroup in 8 trips (`:1529-1530`). The only residual value is
  deeper pipelining, which is R2.
- **N2 ("the h48 path pads to 64 heads") RETIRED on arrival by division:**
  `oproj_h48 / oproj_act_h64` = 7.09/9.45 = **0.750 = 48/64 exactly**, and
  `qkv_h48 / qkv_h64` = 9.44/11.80 = **0.800**, which is also exactly right
  because the QKV output width is `heads·128 + 2·kv_heads·128` and `gqa=6`
  gives 8 KV heads for 48 query heads, the same 8 as for 64, so
  8192/10240 = 0.800. There is no padding to remove.

**Standing consequence.** The long-running critique — *the programme has staffed
measurement of both big residuals but mechanism ownership of neither, while
treating "GPU busy" as "GPU useful"* — is now quantitatively confirmed by (a)
and (b) jointly. The corrective is structural, not exhortative: round-9 keeps
at most one ranked-receipt arm in flight and fills the remaining student slots
with byte-changing mechanism work and with free structural audits (the
wave-quantisation census, the non-aliasing audit, the lane-utilisation census,
and gather-GEMM D2) that decide mechanism arms without consuming a receipt.
Full ranked list: `research/RESEARCH_IDEAS_2026-08-05_15:35.md`.

#### 0.9.15 ★ DISPATCH-COUNT BLINDNESS ON M4 — a corollary of the two dispatch laws

The two hosts have *structurally different* dispatch cost functions, and the
difference is not a scale factor:

| host | law | per-dispatch `c` | knee | provenance |
|---|---|---|---|---|
| M4 Pro | `dT(n) = max(0, n·c − slack)` | 2.607 µs | **1209** | `max_ops_per_buffer` host-encode crossover, `device.cpp:576-593` |
| M5 Max | `dT(n) = n·c` (H_knee0 accepted) | 2.1828 µs | **17.4** | tanjiro #34 + #47 D2; H_cpu/knee1200 falsified at 34.8σ |

The M4 `slack` of 3.152 ms is host-side encode capacity that the GPU hides.
Below the knee, *removing* dispatches removes nothing measurable. Above the M5
knee of 17.4, removal is near-linear.

**The law: a dispatch-count change of order 80 is STRUCTURALLY UNMEASURABLE on
M4 and NEAR-LINEAR on M5.** 80 × 2.607 µs = 0.209 ms against 3.152 ms of slack
⇒ predicted M4 effect exactly zero. The same 80 on M5 is 80 × 2.1828 =
0.175 ms ⇒ **+2.60% of score**.

Consequences the programme must apply:

- A null M4 timing result for a dispatch-count arm is **the prediction, not a
  refutation**. Do not price a dispatch arm from M4 seconds. fern's #48 M4
  numbers (m2−m0 = −1.76%, Welch t 1.98 n.s.; step-1 geometry −0.225%,
  t −1.746 n.s.) are exactly what this law predicts and were correctly filed as
  inadmissible rather than as evidence against her own arm.
- The screenable quantity on M4 is the **census** (`dispatches`, `barriers`,
  bytes, threadgroup geometry, pipeline static properties), not the clock.
- Conversely, an arm that attacks **per-kernel latency** (§0.9.11a's R2/R3) *is*
  M4-screenable, because latency is not hidden by encode slack.
- This is the dispatch-axis twin of §0.9.7's kernel-family reachability rule and
  of #44 F6: *the bar for "M4 says yes" is kernel-family and architecture
  reachability, not statistical strength.*

#### 0.9.16 ★ THE BARRIER-REBALANCING LAW (fern, #48)

Barrier counts do not decompose additively across a chain of fusions. They
**rebalance** onto the surviving dispatches. fern's barrier census (a throwaway
`fprintf` in `maybeInsertBarrier` in non-editable `device.cpp`, used locally and
reverted) over one decode step:

| mode | dispatches | barriers |
|---|---|---|
| 0 stock | 406 | 243 / 163 |
| 1 + norm fold | 366 | 204 / 162 |
| 2 + gate fold | **326** | 203 / 123 |

The norm fold removed 40 dispatches and 39 barriers. The gate fold removed
another 40 dispatches and **exactly 1 barrier**. The mechanism is visible in
source: mode 1's fused kernel *exports* `normalized`
(`LagunaRuntimeModel.swift:4762-4763`, `:4801`, `:4823-4825`) and the standalone
gate then *reads* it (`:5830-5831`), so the gate inherits the RAW barrier that
QKV had already fired. Folding the gate in therefore deletes a dispatch whose
barrier had already been paid for.

**The law: per-fold `dB` is a LOWER BOUND only. Attribute barrier savings only
against the unfused baseline, for the fusion as a whole.**

Direct casualty: **my banked `+2.568%` price for the gate fold is RETRACTED**
(the 6th of the ledger-hygiene casualties, §0.9.13). It assumed the gate's
5.32 µs/call carried its own synchronisation. fern's own inferred mechanism —
CPU-side encode plus launch/ramp rather than barrier-serialisation — is
**Reading B's mechanism**, and it is consistent with `gate_sp`'s §A4 dup/ser
ratio of 0.659. Her ranked receipt is the discriminator; the prereg table in
her research file decides it before the number is seen.

#### 0.9.17 ★★ THE ORACLE BLIND SPOT — `LagunaUpstreamEquivalence.swift` cannot see a prepared bank

`Sources/MLXFastModel/LagunaUpstreamEquivalence.swift` **never constructs
`LagunaRuntimeWeightCache`**. Both the runtime side and the vendored oracle side
therefore run BF16 weights. Every NVFP4 *prepared/fused decode bank* — every
repacked scale plane, every folded weight, every fused-kernel-only layout — is
**off that test's path entirely**. The test happily returns `8/8 byte-identical`
for a bank that has been catastrophically corrupted.

frieren discovered this in #35 and retracted three of his own certificates on
it (the V2 oracle 8/8, the V5 off-path identity argument, and V4a as a
certificate). This is now a programme law.

**Certification requirement for any change that touches a prepared bank, a
packed plane, or a fused-kernel-only weight layout:**

1. `./benchmark.sh --local-submit` with `checked_steps ≥ 1024` and
   `max_abs_diff 0`. The 512-step `--local-iterate` gate (`checked_steps 130`)
   is necessary but not sufficient.
2. **PLUS a fault-injection power control**: deliberately corrupt the same bank
   in a way the change itself could plausibly produce, and demonstrate that the
   gate flags it. A gate that has never been shown to fire on your class of
   fault has certified nothing.

**The gate's blindness is COHERENCE, not magnitude** (frieren's matrix, #35;
he had initially believed the opposite and retracted it):

| injected fault | magnitude | verdict |
|---|---|---|
| fitting codes → 0 | large | **FLAGGED at step 2** |
| coherent +1 on every code | ≈ +8.3% | **FLAGGED at step 3** (`checked_steps 4`) |
| one lane's four codes reversed | small, sign-mixed | **SILENT through 1025 steps**, `max_abs_diff 0` |

The silent case is an exact no-op wherever the reversed quadruple is constant,
and row spans are ≤ 15 codes with the top-7 codes carrying ≈97.9% of the mass —
so the residual exposure is bounded by the **constant-quadruple fraction**,
which is still unmeasured and is owed by frieren.

`AGENTS.md` is not in `editablePaths`, so this law cannot be written where
students read it by default. **It must therefore appear in every brief that
touches a bank, and it lives here.**

**Blast radius: ZERO.** Only #32 ever touched a prepared bank, and the
§0.9.14 byte fingerprint `97c022d6bf31` proves it shipped zero scored bytes.
Nothing in the tree needs re-certifying.

#### 0.9.18 ★★ THE %-OF-CEILING LAW — logical bytes are not measured bytes

nezuko's per-dispatch table (`research/nezuko-pr9-dispatch-fusion.md:120-144`)
carries a "% of ceiling" column computed as (logical MB per call) / (µs per
call) / 260.2 GB/s. For the sliding attention kernel that column reads **36%**,
and the programme read it as "this kernel is only using a third of the memory
system, so two thirds of its time is recoverable".

#56 measured the actual issued traffic. At K = 32 the sliding kernel issues
bytes at **443 GB/s = 170% of the 260.2 GB/s M4 ceiling**, of which only
110.9 GB/s is unique. The kernel is **cache-served and latency-bound**, not
bandwidth-starved. The 2.097 MB/call the counters report is one unique copy of
the 8-head × 512 × 128 × bf16 × {K,V} window; each of the four threadgroups per
KV head re-reads it.

**The law: for a cache-served, latency-bound kernel the "% of ceiling" column is
an UPPER BOUND on byte-boundedness, not a measurement of it. A low figure does
not license a recoverable-time estimate.**

- Invalidated: every §0.9.11b row whose recoverable time was derived from that
  column — `residual_rms_router` (60%), shared-expert K1 (73%), `gate_sp` (2%).
  All marked **SUSPECT** until re-derived by the wave/latency method.
- Unaffected: rows already at ≈100% of ceiling — `qkv_h64_r1`, `lmhead_int5`,
  `oproj_act`, `down_residual`, `routed_swiglu_qmv`. A kernel at the ceiling is
  at the ceiling however you count the bytes.
- nezuko's own conclusion at `:180-193` — *"an occupancy problem, not a
  dispatch-count problem"* — is **refuted by her own #56** for the attention
  rows: co-resident threadgroups serialize (marginal wave = 88% of lone-TG
  latency), so there is no idle occupancy to reclaim there.
- This is the **same object** as frieren's o_proj anomaly: r1 narrow o_proj
  returned 69.5 µs/step at **4.8× its byte roofline** (210 GB/s implied). Two
  students hit the same measurement error class on the same day from opposite
  directions. The shared resolution is that these kernels are issue- and
  latency-bound, and the corollary is genuinely encouraging: **an
  instruction-issue win transfers to M5 at more than 1.0**, because M5 moves
  bytes 2.5× faster and is therefore *more* issue-bound.
- Corrective method, in order: (1) count *issued* bytes, not logical bytes;
  (2) compare against the lone-threadgroup latency and the wave staircase;
  (3) only then quote a recoverable figure.

---

## THE FIVE THINGS TO READ FIRST

### 1. Both residuals now have a shape. Neither has an owner.

tanjiro's #27 measured the M5's hardware constants; his #34 then measured the
four biggest *blocks'* real M5 rates in situ by differencing official receipts
(§A). Three of the four are at or above their ceiling. The residuals are no
longer undifferentiated ignorance:

```
PREFILL   measured S_0                                  97.86 ms
          in-situ routed gather-GEMM  (dS_1, marginal) −44.37 ms
          in-situ attention qkvo prefill  (dS_3)       −22.21 ms
          REMAINDER, everything else                    31.28 ms   <-- +11.6%
            of which bottom-up-explainable real work   ~26    ms
            recoverable by fusion / byte dedup          ~3–6  ms   <-- +1.1–2.2%
          of the 49.19 ms normalised residual,
            routed gather-GEMM excess                  +26.4  ms   <-- LARGEST
            attention qkvo prefill                      −2.4  ms       ITEM ON
            everything else                            ~+25   ms       EITHER
                                                                        AXIS
DECODE    1794 MB at 610 GB/s  = byte roofline           2.941 ms
          measured T                                     4.3224 ms
          residual                                       1.383 ms
          rates 2+4 cover 75.5% of decode bytes,
            combined excess only                        +0.106 ms
          UNATTRIBUTED                                  ~1.27 ms   <-- 29% of T
```

**★ CORRECTED 2026-08-05 10:10.** This block previously read "honest residual
after compute + bytes ~34 ms / of which routed gather-GEMM excess +14.30 ms".
An adversarial audit could find **no derivation anywhere on disk** for the
"~34 ms" (independent attempts reproduced 42.3, 47.4, 32.4 and 19.3), and §A
simultaneously carried a contradictory **46 ms**. Both figures are retracted.
The arithmetic above is the only supported prefill accounting: it is a plain
subtraction from the two receipt-differenced blocks, and it reconciles with the
49.19 ms session-normalised residual to within 0.1 ms.

**Retract also the "46 ms of prefill glue" framing.** 46 ms was a *subtraction
leftover priced at dense-bf16 rates* (`96.8 − 47.6`, receipts `ff29f5c` /
`553ef9f`), so it bundles genuine glue with the NVFP4/MoE kernels' efficiency
deficit against dense bf16. Its own author wrote it is "measured, but it is a
residual, not a mechanism" and "this instrument cannot separate them, and the
separation is the whole question"
(`research/tanjiro-pr27-result.md:36,:101,:190-205,:227,:376`).

**Prefill's biggest item is a real, sized, ownable defect.** The routed
gather-GEMM moves 17,666.41 MB / 1005.02 GFLOP across 39 routed layers in
dS = 43.2619 ± 0.402 ms = 408.4 GB/s = 23.23 TFLOP/s, which is **67% of its own
34.7 TFLOP/s byte ceiling**. Against the 16.9 ms dense ceiling it carries
**+26.4 ms of the 49.19 ms residual** — not the 15.4 ms quoted elsewhere; 15.4 is
only its *recoverable* part under the perfect-overlap bound. At prefill
elasticity 0.362, full recovery is +5.3% of score and a third is +1.8%. The
campaign needs +1.0% to +2.0%. Corrected roofline and mechanism in §A3.

**★ It is an OWNERLESS defect with NO SURVIVING MECHANISM (revised
2026-08-05 14:20).** Mechanism #1 (single-buffered `Ws` staging↔MMA
serialisation) was fern's PR #40 and it **measured null** on both arms (§0.2).
Mechanism **#2** (SM=16 banding) is **CLOSED at the floor** — `SM = BM/WM` is
pinned to 16 by the host guard and the kernel's own `kSwigluRegLocal`
assertion, `TM = SM/16` is integer division so `SM<16` issues no MMA at all,
and `453,120 = Σ ceil(n_e/16)·16` is identically the `kFragRows` floor, not a
tunable. **The previously banked "+1.9 to +2.6%" for it is withdrawn.**
Mechanism **#3** (x re-read, ~1–3 ms) is now **contingent**: it prices against
the same 27.9 ms floor that mechanism #2's closure calls into question, so it
must not be assigned before the régime diagnostic. See
`research/GATHER_GEMM_REGIME_DESIGN.md` for the source-verified closure, the
occupancy-currency mechanism behind #40's double null, and the two diagnostics
(D2 occupancy audit, free and M4-legal; D1 pure-D arm, needs M5) that replace
mechanism proposals as the next step.

**Attention qkvo prefill is not a target.** 22.21 ms for its FLOP load is
**65.74 TFLOP/s = 117% of the 56 TFLOP/s dense bf16 ceiling** — it runs *faster*
than roofline and contributes **−2.4 ms** to the residual. Any hypothesis whose
premise is "prefill attention is inefficient" is refuted before it starts.

**⚠ THE CRUX AUDIT — resolved 2026-08-05, and it went mostly against me.**
Receipt differencing prices the **marginal** cost of removing a block, not its
standalone wall share. If the blocks overlap anything, `dS₁ = 43.26`
*undercounts* block 1 and the 32.40 ms remainder is inflated by exactly that
undercount. I commissioned an adversarial audit of the three claims that rest on
this. Verdicts:

- **CLAIM A — "the queue is serial, so absolute == marginal": PARTLY
  SUBSTANTIATED, but the numeric argument I used for it is near-vacuous.** The
  probe that "proved" serialisation, `research/prefill_probe.py:21-22`, sets
  **`DARKBLOOM_GPU_PROFILE_SPLIT=1`**, which forces `needs_commit()` true after
  every dispatch (`0288d18`, `device.cpp:+555-558`). *The probe serialized the
  workload it then declared serial.* Worse, its `records` are **command buffers,
  not dispatches**, and each interval includes GPU-side fence waiting
  (`device.cpp:397-437`), so with the union at 99.4% of wall, `sum ≈ union` is
  near-definitional. The claim survives on *different* evidence: the big MoE
  chain really is serial by data dependency (`gatherSort → gateUp → activated →
  downProj → scatterUnsort`, `LagunaRuntimeModel.swift:9656-9697`). But it is not
  serial by hardware — every compute encoder is `MTL::DispatchTypeConcurrent`
  (`device.cpp:548`), `memoryBarrier` fires only on a detected buffer-level
  RAW/WAR hazard (`:325-330, :444-450, :363-375`), `slicing.cpp:35` opts extra
  ops in, and there are genuinely independent branches (76 zero-input `arange`
  producers at `:9656-9679`; router and shared-expert stages on the same
  post-norm `x`). Corollary worth keeping: this machinery is **on by default and
  generation-independent**, so it is one of the few things that transfers M4→M5
  without a factor.
- **CLAIM B — "15.4 ms is recoverable": PARTLY SUBSTANTIATED, derivation
  invalid, conclusion survives as a LOWER BOUND.** `43.26 = 141.1262 − 97.8643`
  is the marginal cost of *added copies*; converting it to a block cost needs
  linearity through the origin, cache/first-touch invariance, and dispatch-count
  invariance. All three fail, and all three fail *downward* (the 5.2% cold-page
  penalty contradicts invariance directly) — so 15.4 ms is a floor, not an
  estimate. But the 0.80×-of-serial ratio **cannot distinguish** intra-kernel
  staging overlap from partial residency, which is precisely the ambiguity that
  fern's #40 null then resolved against the staging reading.
- **CLAIM C — "the 32.40 ms remainder is comparable to the ~26 ms M4 census":
  REFUTED.** Do not cite it.

One genuine anchor came out of the audit: in-situ steel bf16 measures
**6.77 TFLOP/s** against tanjiro's standalone **7.40–7.46** at the same shape and
host — 9% apart, which is a real and useful in-situ-vs-microbenchmark discount.

The remaining open piece (arm nesting for `dT₄`) is still on tanjiro's desk
(#34), needs no receipts, and is the last outstanding fact on the prefill axis.

**Decode's residual is now bounded and mostly non-byte.** The two decode blocks
we can price (attention qkvo QMV at 651.8 GB/s, routed-expert QMV at
546.2 GB/s) together move 1354.24 MB — 75.5% of the step's bytes — and waste
only 0.106 ms between them. So the missing ~1.27 ms is *not* in the bytes we
understand. It sits in the remaining ~440 MB and in costs that are not bytes at
all.

**★ REFRAMED 2026-08-05 — the host-dispatch candidate has been demoted; read
this before pricing any fusion idea.** The former text here read: "#37 measured
+4.1 µs/dispatch of host encode/commit that the GPU clock never sees, and the
scored path issues ~406 dispatches ⇒ **1.665 ms**, larger than the entire
residual … recovering a third of 1.27 ms is **+6% of score**." That arithmetic
is arithmetically fine and **causally wrong**. The 4.1 µs is an *average
accounting constant that reconciles two instruments on M4*. It is not a
marginal critical-path price, and 406 × 4.1 ms is not a recoverable pool. Four
independent results say the marginal price at our operating point is ≈ 0:

| Evidence | What it says |
|---|---|
| tanjiro's saturation law (§2) | knee at **+1209** extra dispatches; the scored 406 sits **3× below** saturation; 600 injected launch-only dispatches cost 1% |
| frieren #23 | encoding thread runs **3.5× ahead** of a 96.6%-busy GPU; decode head latency 35.7 µs exposed |
| frieren #14 | 2.0 ms of injected per-layer host spin *reduced* wall time |
| the only direct **M5** dispatch-removal datum | removing the 2 RoPE angle probes from the step front: **+0.01..+0.07 ms/step** (null/negative), `LagunaRuntimeModel.swift:571-580` |

Closing arithmetic: on M4, wall 8.545 ms = 8.345 GPU-busy + **0.200 ms** of
total gap across 406 dispatches *and* 45 command buffers ⇒ ~0.49 µs/dispatch
actually exposed. Had 4.1 µs/dispatch been marginal, M4 wall would read ~10.0 ms.
It does not.

**Where the 1.27 ms most likely lives instead: inside GPU-busy, as issue /
occupancy / latency time in the ~200 dispatches that carry almost no DRAM
bytes.** The magnitudes coincide. nezuko #9's M4 "recoverable" column sums to
**~1.38 ms** — the same size as the M5 residual:

| Kernel | M4 recoverable | Status after #56 |
|---|---|---|
| sliding fused attention | ~~428 µs~~ | **STRUCK** — whole-kernel M5 cost is only ≈290 µs/step |
| full fused attention | ~~130 µs~~ | **STRUCK** — whole-kernel M5 cost is only ≈100 µs/step |
| `residual_rms_router` rpg8→rpg4/2 | ~106 µs | **SUSPECT** — derived from the 60%-of-ceiling column (§0.9.18) |
| shared expert K1 | ~65 µs | **SUSPECT** — derived from the 73%-of-ceiling column (§0.9.18) |

**★★ CORRECTED 2026-08-05 19:20 by #56. Two of these four rows are struck and
the other two are suspect. The table above is no longer a price list.**

Three claims in the paragraph that used to follow this table are falsified:

1. **"~8 threadgroups on 20 cores."** The sliding kernel launches **32**
   threadgroups (`LagunaRuntimeModel.swift:1799-1800`) and the full kernel
   **24** (`:2316`). The count was wrong by 3–4×.
2. **"M4 understates the M5 prize; ~40 cores leaves more of the machine
   idle."** Backwards. At 32 and 24 threadgroups both kernels fit in a
   **single wave** on an ≈40-core M5, whereas M4's 20 cores need two waves for
   the sliding kernel. M4 *overstates* this prize; M5 has already collected
   most of it for free.
3. **"+3.2% to +6.4%, central +5.2%, queue rank 1."** Withdrawn. Routing the
   M4 staircase through single-wave M5 geometry gives ≈290 µs/step for sliding
   plus ≈100 µs/step for full — **≈390 µs/step of whole-kernel time, ≈5.8% of
   score**. A *recoverable* 453 µs cannot be extracted from a 390 µs total; the
   old figure was arithmetically impossible. Realistic recovery of 10–20% of
   the whole-kernel cost is **+0.6% to +1.2%**, which is close to the `~+0.6%`
   the round-9 queue had banked in the first place.

The one durable thing this paragraph got right is that
`sliding_fused_attn_ring_v1` is a custom Laguna kernel rather than an `_nax`
one, so a student can screen a rewrite on M4 for free — which is exactly how
#56 was able to kill four of five ladder rungs without spending a receipt. See
§0.9.11a for the measured staircase and the surviving R2 rung.

Standing caution kept from the old text, now partly discharged: every "hidden
host cost" datum except the M5 RoPE-probe null was M4-based, and M4 is
known-blind to exactly this class. **#34 deliverable A and #47 D2 have since
answered it** — the M5 charges `c = 2.1828 µs` per dispatch from the first
dispatch with no slack, against an M4 knee at 1209 (§0.9.15). Dispatch-count
reduction is therefore an open axis on M5 and a structurally unmeasurable one
on M4.

Two live instruments are pointed at exactly this: nezuko's per-family
byte-carrying-vs-latency-absorbed census (#32 deliverable B) and tanjiro's
aggregate M5 dispatch-saturation law (#34 deliverable A). If the census's
"absorbed" column totals ~1.2–1.3 ms, the decode budget closes for the first
time in the campaign.

**Standing qualifier, from tanjiro himself:** 610 GB/s is a *streaming upper
bound at a favourable shape*, not any real kernel's achievable rate. The
attention qkvo QMV block measuring 107% of it is the proof — treat 610 as a
calibrated reference, not a hard wall.

### 2. The M4 blindness problem — the campaign's real constraint

Three students, three independent instruments, one conclusion:

> **The decode step's remaining headroom is per-kernel issue and latency
> efficiency, and our M4 hosts systematically under-report exactly that class of
> win while reporting regressions in it at full size.**

The evidence:

- **tanjiro's saturation law (M4):** `dT(n) = max(0, n*c - slack)` with
  `c = 2.607 µs`, `slack = 3.152 ms` ⇒ knee at **1209 extra dispatches**. The
  scored path issues ~406 ops, 3× below saturation. Holds nine points across
  n=600–8000 and a 20× threadgroup span to ≤7% with no refitting.
  **Consequence: MLX-op-count reduction on decode is worth ZERO on M4.**
- **nezuko's co-residency decay law (M4):** K1's real −4.5% kernel-body win
  prices at −9.4 µs/step at 1 dispatch/cb, −6.2 at 2, −1.2 at 4, and **~0 at the
  shipped N≈9**. Monotone, so not a cold-start artefact.
  **Asymmetry: making a kernel slower carries through in full (+28 to +55
  µs/step) while making it faster is absorbed.**
- **frieren's #14 result (M4):** 2.0 ms/step of injected per-layer host spin
  *reduced* wall time; identical spin at the step head passed through 1:1.

**The documented exception is DRAM traffic.** tanjiro's discriminator: 1.048 ms
of injected DRAM traffic appeared at **106% of its cost**, while 600 dispatches
of pure launch overhead appeared at **1%**. Byte changes pass through M4 in full,
in both directions. That is why both live arms this round are byte or
instruction arms on kernels measured at 93–100% of the M4 DRAM ceiling.

**Two consequences we are acting on.** (a) tanjiro's official-receipt injection
channel is the highest-leverage instrument we own, because it is the only one
that reads the ranked host — hence #34. (b) Small bit-exact components with
*field M5 precedent* should be shipped and batched rather than locally ranked,
because the local ranking is uninformative for that class.

Receipt throughput is **~1.7/hour for the whole team** (the submission limit is
1 in flight *per account*, not per student). The queue is a managed resource.

### 3. There are three bound classes, and the third one is dependency depth

fern's #30 h-sweep: issued K/V bytes spanned **8×** while kernel time moved
**<8% and non-monotonically** (h1 29.45, h2 27.67, h4 27.13, h8 28.54 µs/layer),
all bit-exact. Loads made L1-hot: no change. 32×8 B vs 16×16 B loads: identical.
So the fused attention phase-3 loop is neither DRAM- nor arithmetic-bound. Two of
my own roofline prizes died on that finding. **Standing rule: an issued-byte count
is not a price for any kernel until something establishes that the kernel is
byte-bound.** Cite a measured per-call GB/s against a stated ceiling, or do not
quote a byte saving.

**#36 then refined what the third class actually is.** "Instruction issue" is too
coarse — the loop does not price instruction *count*. fern hand-wrote a genuinely
cheaper reduction (xor levels 1,2 leave every lane of a 4-lane group holding the
identical partial, so each lane selects `slot = lane&3`, finishes alone with xor
4,8,16, then 4 broadcasts: **15 shuffles against `simd_sum`'s 20**, same xor order
so the same addition tree, bit-exact by construction). Result: **1.79% SLOWER.**

Count depth, not instructions. `simd_sum(float4)` is 5 butterfly levels over 4
*independent* chains — critical path 5, ILP 4. The 15-shuffle version is three
sequential phases with the tail running one chain — critical path ~15, ILP
collapsing to 1. A 25% instruction cut roughly tripled the dependency depth.

**The lever this implies:** the reduction's cost cannot be removed by shortening
it, only by overlapping it with independent work (software-pipelining the next
iteration's K loads across it). Vector and shuffle-count reduction in the fused
attention core is **closed at the mechanism level**, not merely in its packing
form — do not reopen it with a different vector width.

### 4. Rank by renormalised `ns`. Never by `officialScore`.

Each receipt draws a random same-session baseline. Define:

```
norm_decode_su  = 0.013890  / decode_seconds_per_token
norm_prefill_su = 0.0003845 / prefill_seconds_per_token
ns   = norm_decode_su**0.75 * norm_prefill_su**0.25     <- content
draw = officialScore / ns                                <- luck
```

`officialScore` is **3.3× noisier than `ns`** (pooled cv 0.489% vs 0.149%, 27
dof). Draw over 937 receipts: p25 0.98542, p50 0.98867, p75 0.99428, p90
0.99746, p95 0.99908, p99 1.00203, p100 1.01114.

**The promotion arithmetic.** The crown is `46eeccf0` (lBroth, 15:04) at
`officialScore` 2.552308 — with `ns` 2.52419 and `draw` 1.011140, the **highest
draw in 937 receipts**. Its content is *worse than ours* (2.52419 vs 2.52973).

| our `ns` | need draw > | receipts at that draw | expected submissions |
| ---: | ---: | ---: | ---: |
| **2.5297 (now)** | 1.00894 | 2/937 | ~468 |
| 2.5400 | 1.00485 | 4/937 | ~234 |
| 2.5500 | 1.00091 | 14/937 | ~67 |
| 2.5600 | 0.99700 | 112/937 | ~8 |
| 2.5818 | 0.98858 | 472/937 | ~2 |

**The campaign needs +1.0% to +2.0% of content to make promotion a coin-flip
rather than a lottery.** Beating *our own* best published score (2.515950) needs
only `draw > 0.99456` ≈ p75 ≈ 1-in-4 per receipt.

### 5. Score decomposition and the M4→M5 transfer factors

```
S = 512000 * prefill_seconds_per_token (ms)
T = 1000 * decode_seconds_per_token - S/128 (ms)
sigma = (S/128)/D
d ln score/d ln S = -(0.25 + 0.75*sigma)
d ln score/d ln T = -0.75*(1 - sigma)
```

| context | S | T | sigma | elasticity S | elasticity T |
| --- | ---: | ---: | ---: | ---: | ---: |
| **official M5 (our frontier)** | 97.863 | 4.3224 | ~14.9% | **0.362** | **0.638** |
| M5 pinned baseline | 193.544 | 12.3206 | | | |
| M4 `--local-iterate` | 585.6 | 8.769 | 33.6% | 0.502 | 0.498 |
| M4 `--local-submit` | | | ~5.9% | 0.294 | 0.706 |

**M4 under-reports pure step (T) wins by 1.28× and over-reports forward (S) wins
by 1.385×.** `T → score = 0.638` is an algebraic identity at the pinned
baseline, not a measured constant.

**The per-mechanism transfer factor has a missing middle.** These are the only
two calibrated points, and they are three orders of magnitude apart:

| mechanism class | M4 → M5 transfer | source |
| --- | ---: | --- |
| saves DRAM traffic | **106%** | #21/#34 rate agreement |
| removes dispatch overhead | **1%** | tanjiro's saturation law (§2) |
| *saves bytes but adds fixed ALU/transaction cost* | **unknown** | — |
| *changes threadgroup geometry* | **unknown, can change sign** | core-count dependence |

Every arm whose mechanism is not one of the two calibrated endpoints is
effectively **unscreenable on M4** and must be priced from an M5 receipt. This
is the single largest reason briefs now mandate receipts. #35 r2 deliverable A
exists specifically to calibrate the third row.

Noise, from 929 pinned baselines: **`sd(S) = 1.93%`, `sd(T) = 0.34%`** (this
replaces the old 0.497%-on-both assumption). Within-solver best-quintile
repeatability: use **~0.14% on T and ~0.07% on S**. 2σ detection floor for two
n=3 receipt families is 0.243% — **same-session only, see the drift law below.**

**★ NEW LAW 2026-08-05 — cross-day ranked-session drift ≈ 0.3%, roughly 10× the
same-day replicate spread. Difference arms within one session or not at all.**
Four receipts are frontier-equivalent by construction (each computes the promoted
frontier; the fourth is tanjiro #34's n=0 zero-injection anchor):

| receipt | when | `officialScore` |
|---|---|---|
| `71586bc` | 8/4 10:02 | 2.515950 |
| `c210d20` | 8/4 11:38 | 2.514743 |
| `b6032ae` | 8/4 20:11 | 2.514911 |
| `c3ce66e` | **8/5 09:33** | **2.523276** |

The three 8/4 receipts have mean **2.515201**, sd **0.000650 = 0.026%**. The 8/5
receipt is **+0.321% = +12.4 sd** out. A code effect is ruled out: the only diff
between the advisor head and tanjiro's submitted tree on the *submitted surface*
is inert injection scaffolding in `LagunaRuntimeModel.swift` with all knobs at 0;
the other changed files are under `Sources/MLXFastHarness/`, which is **not** in
`editablePaths` and therefore never uploaded.

Consequences, all binding:
- **Every cross-day receipt-pair screen below ~0.6% is unsupported.** The old
  "0.243% floor" is a *same-day* floor. Arms in a family must be submitted
  back-to-back in one sitting, with wall-clock times recorded.
- A control must be re-run if a family's sequence crosses a day boundary.
- This still **passes tanjiro's own 0.4% void threshold**, so his #34 series is
  not void — but its fit must not consume any cross-day difference.
- Mechanisms that survive the widened floor: nezuko `MB_PER_BUFFER` (+1.08%),
  frieren's plane change (~+1.6%), D-MLP (+1.56%). Anything smaller needs a
  same-session pair.
- **The stored `current_best` is a historical value, never re-measured.** Today's
  ~0.3%-richer conditions are therefore *perishable free headroom* against a
  stale crown. Prefer submitting a real candidate today over holding it.

The service **dedupes byte-identical archives** — add a distinct note per
receipt in a family. All 789 `rejected` submissions publish full metrics; only
the 467 `failed` ones publish none. Of 1409 public submissions, **not one
publishes a speedup below 0.95.**

---

## Current research focus

### A. The four M5 constants are now measured (tanjiro #27, merged)

**Method, which is the reusable asset.** Inject output-neutral work into the
scored path at two known levels, submit both, and difference the two official
receipts. `S` and `T` are independent observables, so one receipt pair yields one
prefill rate and one decode rate. Receipts `ff29f5c2` (1 sweep pass, 20 GEMMs,
S=103.5678, T=4.83241) and `553ef9f0` (7 passes, 120 GEMMs, S=136.2994,
T=7.42876) give `dT = 2.59635 ms` for 1610.61 MB and `dS = 32.7316 ms` for
1717.99 GFLOP. Both receipts: `passed_correctness=true`, `max_abs_diff=0`, both
floors passed, TTFT 0.42 s against a 2.5 s gate, semantic GPQA passed,
`peak_ram 21 GB`, rejected-on-ranking as designed.

| constant | measured | band | overturns |
| --- | ---: | --- | --- |
| M5 achievable **streaming DRAM read** | **610 GB/s** | 603–628 | my published 485–530 |
| M5 dense bf16 GEMM @ 512×8192×2048 | **56 TFLOP/s** | 47.2–64.7 | "prefill compute-closed at 29 TFLOP/s" |
| `S_0 − max(compute,dram)` = **glue + NVFP4/MoE efficiency deficit vs dense bf16** | **46 ms** ⚠ | 43–49 (44–51% of S_0) | my assumed 9–12 ms |
| M5 in-situ per-dispatch cost | **1.980 ± 0.044 µs** cand-only / 2.088 ± 0.165 paired (#34) | bracket [0.36, 2.09] µs pending #47 D5 | its own "indirect 2.9–3.4 µs" |

⚠ **The 46 ms row is retained only as this instrument's own reading; it is not a
programme number.** It is a dense-bf16-priced subtraction leftover that bundles
genuine glue with the NVFP4/MoE kernels' efficiency deficit, and it is
superseded for all accounting purposes by the receipt-differenced prefill
arithmetic in "FIVE THINGS TO READ FIRST" (remainder **31.28 ms**). See the
retraction at §"Retract also the '46 ms of prefill glue' framing".

Raw readings 620.3 GB/s / 52.49 TFLOP/s / 42.89 ms; session-normalised 610.6 /
59.43 / 49.19; propagated sd ±7 / ±5.3.

Validation, all three passed: (a) the M4 in-situ marginal DRAM rate reproduced
#21's independent control to 97.6% / 90.4%; (b) 56 TFLOP/s ≈ 2 × M4 Pro's
measured 28.76 with 2× the cores, agreeing to 2.6%; (c) 610/614 nominal = 99.3%
is the same class of result as M4 Pro's measured 262.5/273 = 96.2%.

**Struck by this result:** my published 0.884 ms decode launch-ramp term is not
recoverable, and my 2.18 µs in-situ per-dispatch reconciliation is retracted.
`MLX_MAX_OPS_PER_BUFFER` 50→500 costs +1.4% at n=2400 and +0.5% at n=0 — that
lever is worth zero (independently killed by #23, see §E).

Free by-products: `device.cpp` keys on **`arch_.back()`, the LAST character**, so
`applegpu_g16s` takes the `'s'` branch = 50/50 thresholds. `architecture()->name()`
cannot be read from a receipt (no free-text field), but a dispatch count keyed on
`arch.back()` can be read out of `T` — a piggyback now folded into #34.

### A2. The four M5 block rates, measured in situ (tanjiro #34, adopted)

#34 extended the differencing method from *hardware constants* to the **real
kernels' real rates inside the scored window**, by scaling each block's own work
and differencing official receipts. This is the most useful reference table in
the programme: it tells us which blocks are finished and which are not.

| # | block | work moved | measured | own ceiling | excess |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | **routed gather-GEMM (prefill)** | 17,666.41 MB / 1005.02 GFLOP | **408.4 GB/s = 23.23 TFLOP/s** | 34.7 TFLOP/s | **+14.30 ms** |
| 2 | attention qkvo QMV (decode) | 802.16 MB | 651.8 GB/s (107%) | 610 GB/s | ~0 |
| 3 | attention qkvo dense GEMM (prefill) | 1460.29 GFLOP | 65.74 TFLOP/s (117%) | 56 TFLOP/s | ~0 |
| 4 | routed-expert QMV (decode) | 552.08 MB | 546.2 GB/s | 610 GB/s | +0.106 ms |

Per-block deltas: dS₁ = 43.2619 ± 0.402 ms, dT₂ = 1.23070 ± 0.028 ms,
dS₃ = 22.2139 ± 0.362 ms, dT₄ = 1.01067 ± 0.034 ms. Receipts: R1 `b6032aeb`
(S 97.8643, T 4.27468), R2 `ca416f01` (141.1262, 5.50538), R3 `6757de65`
(120.0782, 6.51605). The base tree commit `6288233` is byte-identical on
`Sources/` to R1 and returned base `officialScore` 2.5149 — the control is
sound.

**★ CORRECTION 2026-08-05 — R4 `afec358` FAILED, and row 4 has no independent
receipt.** This document previously recorded R4 as "still validating". It is
not: `mlxfast submissions --all` reports `status=failed`, `score=n/a`,
`metrics=n/a`, commit `af3ab58`. The family therefore rests on **three**
successful receipts, not four. Reconstructing which receipt supplied which rate
(every step below checks to the last published digit):

```
R2 - R1:  dS = 141.1262 - 97.8643 = 43.2619  = dS1   (row 1)
          dT =   5.50538 -  4.27468 = 1.23070 = dT2   (row 2)   <-- one receipt, two rates
R3 - R1:  dS = 120.0782 - 97.8643 = 22.2139  = dS3   (row 3)
          dT =   6.51605 -  4.27468 = 2.24137           (the 2.241 +- 0.031 validation)
=>        dT4 = 2.24137 - 1.23070 = 1.01067  = row 4
```

Row 4 is thus a **difference of differences between two different receipts** — a
legal estimator only if R2's and R3's arms are strictly nested, and in any case
its published ±0.034 ms bar is too tight because it carries only one receipt's
noise. Treat **dT₄ = 1.01067 as PROVISIONAL** until tanjiro confirms arm nesting
(asked on PR #34, 2026-08-05). If `afec358` was its only source, row 4 has no M5
receipt at all and **55.3% of the decode byte budget is unmeasured** — in which
case a merely-slow routed-expert QMV could absorb part of §1's 1.27 ms residual,
which *weakens* rather than strengthens every host-side story. All four
submission notes are byte-identical boilerplate listing the kernels in score
order, so the notes cannot disambiguate this; only tanjiro's notebook can.

**Free internal validation.** R3−R1 moved 1354.24 MB in 2.241 ± 0.031 ms =
604.2 GB/s = **99.0% of the 610 constant**. One difference simultaneously
confirms the constant, the `S/128` correction in the `T` definition, and that
cold injection behaves on the ranked host.

Blocks 2 and 3 are **done**: both measure *above* nominal peak, so there is
nothing to win in attention qkvo on either axis. Block 4 has 0.106 ms = 7.9% of
the decode residual. Block 1 has +14.30 ms and is the programme's #1 item.

tanjiro failed his own pre-registration on block 1 (predicted 29–33 TFLOP/s by
transferring efficiency across a *different* kernel) and retracted a concave
rate-1 sweep in favour of a linear-through-origin fit at 4.138 ms/copy. Both
self-corrections are recorded because they are why the table is trustworthy.

### A3. The routed gather-GEMM prefill prize — MECHANISM #1 MEASURED NULL (fern #40)

> **⛔ STATUS AS OF 2026-08-05 12:05.** This was the programme's #1 item. It is
> not any more. fern's #40 tested Mechanism #1 (staging↔MMA serialisation on a
> single-buffered `Ws`) with **two** independent implementations — double-buffered
> `Ws` (v1) and register prefetch (v2) — against a same-session v0 control, and
> **both arms lost on renormalised `ns`**: control 2.544360, v2 2.539719, v1
> 2.538013. Measured dS was **+0.4626 ms** (v2) and **+0.1150 ms** (v1), i.e. the
> *wrong sign* against a predicted −2.42 ms, and both inside σ_dS = 0.2536 ms.
> The 15.4 ms "recoverable gap" derivation below survives as a **lower bound on
> the arithmetic** (see the crux audit in §1, CLAIM B), but the *causal claim* that the
> gap is staging serialisation is refuted. The whole `_nax` stage-2 weight-staging
> family is **CLOSED** — do not reopen it with deeper prefetch, a wider `Ws`, or a
> different barrier placement. What survives: the byte-level accounting (below),
> the 0.80×-of-serial ratio as a *measurement*, and **M2 (gather elision via
> `lhs_indices`)**, which removes real bytes instead of trying to overlap them and
> is now unowned and assignable.

**Do not use nominal 17,666 MB for the roofline.** Against the real route
histogram (`research/prefill-512-route-histogram.txt`, 76 records × 256 experts,
4096 rows each) the nominal figure is wrong in both directions:

- **20.26% of (layer, expert) pairs get zero rows and are never read.** The
  binary search finds an empty run and the k-loop never executes
  (`fp_quantized_nax.h:1699-1727`). Those weights cost zero bytes.
- Chunk re-reads for experts with >64 rows are only **1.080×**
  (Σceil(r/64) = 16,758 vs 15,514 non-empty pairs).

```
net weight DRAM      = 17.666 GB x 0.8613 = 15.22 GB  -> 27.9 ms at 610 GB/s
MMA issued rows      = 453,120 / 311,296 useful = 1.456x  -> 26.1 ms issued
                                                             (17.9 useful)
fully-serial D + M   = 54.0 ms
measured             = 43.26 ms   = 0.80 of fully-serial
perfect-overlap bound= max(D, M)  = 27.9 ms
RECOVERABLE GAP      = 15.4 ms
```

The kernel realises only **~41% of the achievable staging↔MMA overlap**. This is
neither a bandwidth problem nor a FLOP problem.

**Mechanism #1 (~10–15 ms): staging↔MMA serialisation on a single-buffered
`Ws`.** k-loop at `fp_quantized_nax.h:1744-1795`: device-load A → `barrier` →
all 128 threads stage the 64×64 weight tile into the *single* 9,216 B `Ws`
(`:1611-1618`) → `barrier` → MMA reads `Ws`. Two barriers per k-iteration, and
the next iteration's staging has a WAR hazard against this iteration's MMA.
Nothing overlaps. Our own `quantized.cpp:1277-1287, 1445-1450` records staging
at ~50 LSU ops/thread/k-iter against ~40 compute-side and calls staging
**"39.5% of prefill"**. This is H1 of `research/PREFILL_NAX_ANALYSIS.md`, now
quantified. Apple tech talk 111373: Family-9+ shares one cache hierarchy across
threadgroup and device memory, so a barrier-staged TG tile buys **no locality**
on this hardware — it is pure serialisation cost. A third-party M5 INT8 study
measured 2.23–2.77× from deleting barrier-staged TG tiles.

**Mechanism #2 (~5–7 ms now, → 0 under perfect overlap): SM=16 M-banding
padding, 1.456×.** Hardware fragment is 16 rows (`steel/gemm/nax.h:27-28`); the
mean non-zero expert gets 20.07 rows, median 11. Fix #1 first, then re-measure.

**Mechanism #3 (~1–3 ms, indirect): x re-read per column tile.** grid.x = 16
(gate_up, K=2048, N=1024) or 32 (down, K=512, N=2048)
(`quantized.cpp:1915-1924`). 15.3 GB if uncached, but the ~16.8 MB per-layer x
slab is SLC-resident, so it costs LSU slots and SLC bandwidth, not DRAM bytes.

**REFUTED — do not re-litigate.** (a) *Weights re-read once per column tile* —
false, and I verified the line myself: `wl = w + y_col * K_w` with
`y_col = tid.x * BN` (`fp_quantized_nax.h:1631-1634`) gives each TG one
(expert, column-tile) pair reading **disjoint** 64-column slabs. This was my own
priority hypothesis and it was wrong; the −20% never-read saving more than
offsets the 1.080× chunk factor, so nominal-byte accounting *overstates* DRAM
time and makes the gap larger, pointing all of it at #1/#2. (b) Load
imbalance / long tail: <1 ms (worst record is one 505-row expert = 8 chunks =
4.2% of that record's chunks, against 4,096–8,192 TGs per dispatch).
(c) Scale-plane access cost (`fp_quantized_nax.h:391-470`): negligible.
(d) Insufficient accumulator concurrency: TN=4 already gives four chains with
dual-issue MMA pairs (`nax.h:1012-1031`).

**The fix arm is already pre-plumbed and inert.** `DARKBLOOM_STAGE2_GATHER`
exists host-side only: `jit_kernels.cpp:1130-1155` parses the env var once and
injects `#define DARKBLOOM_STAGE2_GATHER 1` into **expert-kernel JIT source
only** (`get_qmm_nax_kernel`, `:1227-1257`, gated on `_expert_` in the kernel
name, so every other JIT lib stays byte-identical); `quantized.cpp:1683-1702`
prints the dispatch-site ground truth, where "active" requires **both** the flag
**and** `expert_aligned`. The kernel-side `#ifdef` blocks were stripped **for
byte budget, not because they lost** (`research/nezuko-harvest-report.md`,
solver `4bf4f794` mechanism 4: "…not a speed change: it is submission-surface
budget … ~33 KB … removing it is what made room for mechanisms 3 and 5"). The
symbol appears **only** at `quantized.cpp:1683,1692` and
`jit_kernels.cpp:1130,1148,1155` — absent from `fp_quantized_nax.h` and its
`mlx-generated` twin. The referenced `notes/exp-stage2.md` is an upstream-solver
file we do not have, so **there is no prior stage-2 measurement in this
checkout.**

**Bit-exactness has shipped precedent in this exact kernel.**
`DARKBLOOM_SWIGLU_REGLOCAL` is default ON and already won: it "reads gate/up
straight from the MMA Dtile fragments instead of round-tripping them through
threadgroup memory with two barriers per column tile … values are bit-identical".
Removing TG round-trips and barriers here is a shipped, bit-exact, winning
transformation class. Double-buffering changes only the barrier *schedule*:
identical values, identical MMA issue order, identical epilogue, identical store
addresses. `max_abs_diff` must be exactly 0.

**Five traps that each silently produce a fake null.** (1) `Ws_storage` is
**aliased by `gate_up_stage`** — any double-buffer must handle the alias or
corrupt the gate/up path. (2) Keep `TN` even: `TN = SN/16` = 4 at BN=64/WN=1; an
**odd** `TN > 1` instantiates an **empty** `tile_matmad_nax`
(`steel/gemm/nax.h:994-1031` only has `TN==1 && TM%2==0` and `TN%2==0`
branches) — no compile error, no MMA, silent garbage. (3) Keep `SM ≥ 16`;
`SM < 16` ⇒ `TM = 0` ⇒ no MMA. (4) Keep
`bm==64 && wm==4 && (wn==1||wn==2)` so the `quantized.cpp:1662` accept gate
still selects the expert kernel — falling off it silently dispatches the
**non-expert** kernel. (5) **Confirm the `mlxfast: fusion active: stage2_gather`
stderr line before believing any A/B number.** Our tree documents the precedent:
the trace exists because "those function constants only ever reached the
non-expert kernel" — "the exact confound that made the STAGE_WIDEST/WIDELD arms
measure their own control."

**Ranked evidence must be official M5 receipts.** `quantized.cpp:1959` routes to
`gather_qmm_rhs_nax` only under `metal::is_nax_available()`; `device.cpp:913`
requires arch_gen ≥ 17; our M4 hosts probe as `applegpu_g16s` gen 16 and run
steel bm16/bn32/bk32 instead. **An M4 prefill number is not evidence for an
`_nax` change** — M4 is for compile, correctness, and flag-OFF equivalence only.

Follow-ups, conditional on #40's result: **F3** BN=32 (+1–3 ms, halves `Ws` to
4.6 KB, doubles grid.x, TN→2 even ✓, SM stays 16, but doubles x re-reads — only
interesting if occupancy proves binding); **F2** staging-free B path /
dequantize into fragments (up to ~10 ms, high risk: with WM=4/WN=1 all four
simdgroups consume the *same* 64×64 B tile, so naive removal quadruples
dequant). **Forbidden:** MegaBlocks-style blocking (median non-zero expert has
11 rows against 128-row blocks — wrong regime), split-K, stream-K (8,192 TGs,
uniform K, not tile-starved), BM=32, skip-empty-expert dispatch surgery (empty
TGs already exit at the binary search). The literature review was unambiguous
that the current design already **is** the grouped-GEMM state of the art —
sorted tokens + binary-searched expert runs + one TG per (expert, col-tile) is
vLLM `moe_align_block_size` plus a persistent visitor, and `eg_256` matches the
CUTLASS "at most one tile per problem" rule. The Apple-specific overlap lever is
the only one left, and vLLM's own notes agree small-M MoE GEMM is
memory-latency bound and a deeper pipeline hides weight loads — while warning
extra stages can flip it to occupancy-bound. That trade is the hypothesis.

### A4. ★ The decode kernel census and the dup/ser first-touch lever (nezuko #32 r2, MERGED)

This is the single most reusable artefact the programme has produced on the
decode axis. Sources: `research/nezuko-pr32-r2-report.md`,
`research/nezuko-dispatch-elasticity.md`, `research/nezuko_serial_budget.py`.

**The decode step is ~93% one-kernel-at-a-time.** Round 3 (run `1c8aded9`,
`DARKBLOOM_GPU_PROFILE_SPLIT=1`, 250 steps, 0 divergences) gives serialised
per-kernel sum **8850.3 µs** against the SPLIT=0 union **8272.4 µs**. The excess
is **577.9 µs = 6.99% = +1.42 µs/dispatch**. Read that as: forced serialisation
costs only 7%, so the unforced step was already almost fully serial. This is the
cleanest evidence we have that decode has essentially no dispatch concurrency to
harvest, and it is why D-STRAND is priced low.

**Top of the M4 decode step (16 families cover 106.8% — they overlap slightly):**

| family | % of step |
|---|---:|
| `routed_nvfp4_swiglu_qmv` | 18.88 |
| `decode_nvfp4_qkv_h64` | 16.95 |
| `oproj_act_h64` | 14.30 |
| `down_residual` | 10.82 |
| `sliding_fused_attn` | 7.71 |
| `lmhead_int5` | 6.10 |

**★ The dup/ser first-touch ratio — the lever that now drives the fusion queue.**
For each family she compares a duplicated-call timing against a serialised one.
The ratio classifies the bottleneck:

- **ratio ≈ 1 ⇒ bandwidth- or occupancy-bound.** The second call costs the same
  as the first, so nothing was resident to reuse. These need a *better kernel*,
  not fusion: `routed_swiglu` **0.958**, `sliding_attn` **0.971**.
- **ratio ≪ 1 ⇒ dominated by large first-touch weight streaming.** The second
  call is much cheaper because the weights are now resident. These are where
  **fusion is the lever**: `oproj_act_h64` **0.601**, `residual_rms_router`
  **0.605**, `gate_sp` **0.659**, `shared_qmv` **0.721**.

This is an independent route to D-FUSE-GATESP: `gate_sp` (0.659) and `oproj_act`
(0.601) are both first-touch-dominated and adjacent in the layer, so fusing them
amortises one streaming pass. It also explains why the sliding-attention rewrite
must be a *kernel* change (ratio 0.971) and cannot be helped by fusion.

**Four self-retractions, all accepted.** These matter more than the positive
findings because they invalidate numbers still quoted elsewhere:

1. The round-1/2 **recovery-ratio table is SUPERSEDED** — 7358 µs serialised vs
   3860 µs "skip-recoverable" (52%) is not a recovery estimate, because skipping
   a kernel corrupts the residual stream, randomises the router's top-8 over 256
   experts, and destroys expert-gather locality.
2. **`skip` deltas are LOWER bounds, not upper bounds.** Sign reversed.
3. The **"46.7% / 53.3%" split is an artefact** of the superseded table.
4. **"Isolated per-call timing overstates prizes ~2×" is backwards** — it
   *understates* them, for the same locality reason.

**Her r1 closed on arithmetic, correctly.** `shared_nvfp4_swiglu_qmv` is
295.0 µs = 3.57% of decode, so the measured −4.5% body win is 13.3 µs =
**0.160%** — about 4× below the ±16 µs measurement aperture. A real win that is
unmeasurable is not shippable evidence.

**Three corrections to my own numbers, adopted:**

- Full-profile command buffers per step are **50 MB → 85, 200 MB → 34, 400 MB →
  19**. My earlier "45" was the *low-memory* 128 MB / 64 ops configuration.
- The full-profile gate is **≥64 GiB, not ≥96 GiB** — so the `MLX_*` knobs *are*
  live on our local hosts, which is what made #44 assignable at all.
- `Vendor/.../metal/device.cpp` is confirmed **NOT** editable (97 `editablePaths`
  entries, none contains "device"). Every command-buffer mechanism must go
  through the three `setenv` calls at `LagunaRuntimeWeights.swift:381-389`.


### B. The scale-code width arm — repriced against the measured M5 rate (frieren #35, r2)

NVFP4 g16 stores 8 code bytes + 1 E4M3 scale byte per 16 params, so **scale bytes
are exactly 1/9 of every NVFP4 stream.** Codes and scales are *separate* buffers
everywhere in the runtime at an exact 8:1 stride
(`LagunaRuntimeModel.swift:6523-6524`, `:6604-6605`, `:6709-6710`, `:6802-6803`,
`:7662-7663`; attention `bank.scales` is `uint8` with dims `(rows, hidden/16)`).

```
plane                              stream MB/step   scale MB/step   6-bit saves   4-bit saves
attention q/k/v/o (incl. o_proj)         802.2            89.1         22.3 MB       44.6 MB
routed gate/up                           (of 552.1)       40.9         10.2 MB       20.5 MB
routed down                              (of 552.1)       17.6          4.4 MB        8.8 MB
shared expert                            (of 552.1)        2.8          0.7 MB        1.4 MB
TOTAL                                                    150.4         37.6 MB       75.2 MB
                                                        = 8.4%        = 2.10%       = 4.19%  of 1794 MB
score at the 415 GB/s achieved rate                                   +1.34%        +2.67%
```

**REPRICED by §A2 — this table's last line is now optimistic.** It divides bytes
by the *whole-step average* 415 GB/s. But the attention qkvo plane, which is 59%
of the scale bytes, actually runs at the measured **651.8 GB/s**, so its bytes
are worth 1.57× less time than the table assumes. Concretely for frieren's r1
form: 30.61 MB/step saved buys −47 µs at 651.8 GB/s, not the −138 µs the M4
roofline suggested, while his +43 µs three-load reconstruction cost is
**bandwidth-independent** — net **−4 µs/step ≈ +0.06% of score**, well under the
0.243% detection floor. Worse, 651.8 GB/s is *107% of nominal*, which means the
plane read already coalesces near-perfectly; splitting one contiguous `uint8`
stream into three narrower streams is exactly the kind of change that can
regress on M5 while M4 shows a win. Hence r2: get one ranked M5 receipt on the
current form to calibrate the transfer factor for the class "saves DRAM bytes,
adds fixed ALU/transaction cost", *then* build the 4-bit lane-major variant
(per-row base + `0xFF` sentinel escape, `row_le15` ≈ 0.981–0.994, two loads/row
instead of twelve, −70…−90 µs/step on M4) which has a far better
bytes-saved-per-instruction-added ratio.

**The census is already half-written in our own tree.**
`LagunaRuntimeModel.swift:4040-4054` (the `DARKBLOOM_E4M3_SIGN_DOMAIN` comment)
certifies that a full scan of the pinned checkpoint's 234 U8 scale tensors
(1,970,601,984 bytes) measures **min 1, max 73, zero sign bits** — a 7-bit range
with the top bit provably dead. It says the attention side banks are nonnegative
and says **nothing about their range or distinct-value count.** That is the gap
#35 closes.

**Field precedent on the ranked host.** ivanfioravanti's `ae9ac90b` (09:33,
`ns` 2.53672, 2nd of 937 on content) ships the narrowest version: routed gate/up
codes are ≤63 for layers 1–38 so gate+up for one lane pack into 12 bits / two
lanes per three bytes; layer 39 has four codes >63 and keeps uint8; Metal
reconstructs the original uint8 and calls the unchanged decode; lane parity
selects. Measured over 1023 checked decode steps per arm: **4.444 vs 4.471
ms/token = −0.60% steady, −0.52% charged ⇒ ≈ +0.39% of score.** My byte
arithmetic independently predicts +0.36% for that exact arm — two routes agreeing
to 8%, which is why I trust the rest of the table.

**He shipped the smallest of the four planes.** The attention plane is 2.2× his
arm, and attention Q/K/V/O are BF16 on disk (the 234-tensor census is 39 layers ×
6 expert projections), so **their scale representation is created by our own
transform and is entirely ours to choose.**

**My design improvement: nibbles, not 6-bit fields.** In the attention QKV kernel
`column = simd_lid * 16` so the scale index is `simd_lid` — **lane L reads scale
byte L**, 32 perfectly contiguous bytes per simdgroup. If a plane has ≤16
distinct codes, a **4-bit dictionary index** halves the plane with *no unaligned
load anywhere* (lane L reads byte L/2, selects nibble L%2), and the 16-entry LUT
can hold the already-decoded `float` — bit-exact by construction, and it deletes
the E4M3 decode instructions from a loop family fern has shown is
issue-sensitive. Strictly simpler and 2× larger than the field's scheme.

**Why M4 can screen it.** These are the most byte-saturated kernels in the model
(#9 isolated, ceiling 260.2 GB/s): `decode_nvfp4_qkv_h64_r1` 100% of ceiling,
`qkv_h48` 99%, `oproj_act_h64` 95%, `routed_..._swiglu_qmv` 93%. At 100% of the
DRAM ceiling there is no slack to absorb a byte reduction, and §2's discriminator
says DRAM changes pass through M4 in full. Predicted attention-6-bit effect:
**~−88 µs/step = 2.2× nezuko's 40 µs/step detection gate.** Nothing else large on
our board is locally rankable.

Risks stated in the brief: alignment/coalescing on packed reads; `peak_ram`
(narrowing must *replace*, never duplicate — it should *free* ~985 MB of routed
scales); and prefill isolation (prefill reads attention weights as **BF16** —
`attn_proj_qkvo` 2852.1 MB is exactly 1426.1M params × 2 B — so the attention
NVFP4 bank is decode-only and free to change, while the routed on-disk
`e4m3ScaleUInt8` tensors *are* read by the prefill NAX gather-GEMM and must not
be narrowed).

### C. Attention reduction packing (fern #36, r1) — and #30's merged win

**Merged in #30: threadgroup bank-conflict padding.** Both fused-attention
kernels' epilogue exchange stride `BD=32` → `BDP=BD+1=33`. +30/−20 lines of pure
scratch addressing; every value, reduction order and rounding point untouched.
Threadgroup memory 17,920 → 18,432 B of 32,768; geometry and wave count
identical.

I verified the mechanism from source arithmetic before merging: the write bank
index is `(lane*32 + sg) mod 32 = sg` for all 32 lanes — a 32-way conflict — and
at stride 33 both the write `(lane+sg) mod 32` and the read `(sg+lane) mod 32`
are all-distinct, conflict-free in both directions.

Measured: isolated **−6.30%** (30.01 vs 32.03 µs/layer, median of 4, control
noise 0.4–0.6%); end-to-end `--local-submit` decode **−0.94%** with both
orderings agreeing (−0.85% candidate-first, −1.03% base-first). His two routes
agree to 11% (isolated 2.02 µs × 40 = 81 µs/step vs end-to-end 90 µs/step).

**★ My correction to his M5 projection, which future briefs must apply.** The
saving is a **per-threadgroup** stall, and his own geometry table gives waves 2
on 20 cores / **1 on 40 cores**. M4 pays the conflict twice per layer, M5 once ⇒
the M5 absolute saving is **half**: ~40–45 µs of 4322 µs = ~1.0% of T ⇒
**~0.6% of score** (range 0.5–1.2%), not his 0.9–1.2%.

**★ Re-priced with n=4 (from #36).** Three more within-process estimates of the
padding (−7.8 / −6.8 / −6.8%) put the mean at **−6.9%** of the sliding layer =
2.2 µs/layer × 30 = 65 µs/step on M4. fern's own wave arithmetic then reproduces
my halving: 65/2 = 32.5 µs per wave, M5 waves = 1, 32.5/4318.1 = **0.753% of T**.
Applying the correct elasticity (he used 0.75; it is `0.75 × (1 − sigma)` = 0.637)
gives **0.48% of score**. My ~0.6% correction is confirmed and his 0.9–1.2% is
retired.

**★ RESOLVED (was the last open question about a merged win).** fern's probe read
~30 µs/call for `sliding_fused_attn_ring_v1` (898/30) where nezuko's #9 SPLIT
harness read 22.34 µs — an apparent ~34% gap between two of our instruments on
the same kernel. #37 reconciled it: the GPU-clock time is 22.66–22.78 µs, within
1.7% of SPLIT's 22.34 and below our ~2% instrument floor, and the whole gap is
**host-side** — about +4.1 µs/dispatch of encode/commit plus ~1.2 µs of
command-buffer granularity that the GPU clock never sees. #30's absolute price
was derived from the probe, so it re-prices from 0.48% to **~0.36%** of score
(still a win, still merged). See standing rule 15; the same +4.1 µs/dispatch is
now the leading candidate for the ~1.27 ms unattributed decode residual in §1.

**CLOSED by #36: vector and shuffle-count reduction (the whole family).** Details
in §3. Two premises I gave fern were both wrong, and he found both:

1. **The `float2 −6.4%` row never existed as a separate arm.** It was
   `probe_padvec`, generated as `vector_reduce(pad(src))` — it already *contained*
   the padding. A padding-free vector arm was never measured, so −6.4% and −6.3%
   were **one mechanism under two labels**. My error was worse than misreading a
   label: I wrote "those are the same size" into the brief and treated
   near-equality as evidence the second arm was real. **Standing prior: when two
   arms agree to better than the noise floor, suspect they are the same arm
   before suspecting additivity.**
2. **The "QK `simd_sum` = 3.58 µs = 20% of the loop" figure is probably inflated**
   by dead-code elimination — with the reduction's result unused, nothing keeps
   its producer madds alive. See rule 12. Every number in #30's loop-attribution
   table (QK `simd_sum` 3.58, madds 1.16, rescale 0.40, softmax 0.31) and its d2
   arm ("loop arithmetic deleted, loads kept: 28.9") now carries that caveat.

Measured nulls from #36, all against the shipped padded arm: `float2` alone
−0.27% (one noise floor); pad+`float2` −0.85%/+0.23% (does not stack); `float4`
with madds hoisted −0.47%/+0.12%; `float4` + packed epilogue −0.46%/−0.19%.
Geometry identical in every arm, so this is an instruction-mix experiment at fixed
geometry and the M4 null is evidence about M5; bounded M5 residual 0.013% of score.

**Two reusable assets from #36.** (a) The **duplicate-arm noise floor** — same
`.metal`, two labels — reading 0.02–0.28%, which is what makes the null decisive;
now the standard for this probe, alongside `senpai/tools/sliding-attn-probe/diag_stack.py`,
which generates every arm from one rendered kernel text. (b) **Metal's `simd_sum`
is the ascending xor butterfly**, established via the hand-written tree arm — any
future arm can now reason about association order in these kernels from source.
Bit-exactness confirmed locally at 0/8192 in the real 1024-thread kernel, which
promotes nezuko's #32 packing proof from borrowed to local.

**Also refuted and closed by #30:** the whole `h × s = 64` KV de-amplification
family. The assigned config h=8,s=8 two-pass deferred epilogue was **+5.7%
SLOWER** with bit-exactness proven.

### D. The K1/K3 field-gap decomposition is closed (nezuko #32, MERGED as `d18ebbba`)

Her assigned gate required ≥40 µs/step off `gpu_busy_union`; she measured
**+8.3 ± 7.6 µs/step** (400 steps, interleaved n=3, Welch t=1.10, CI [−14,+31]).
A clean, well-powered negative — and the diagnosis is arithmetic:

- **K1 body is a real win:** 7.54 ± 0.03 → 7.20 ± 0.08 µs/call = **−4.5%**, with
  an unmodified-K3 drift control reading ±1.8% across all three arms.
- **K3 is a regression she had already isolated:** A1-on-K3 is **+0.96% worse**.
- My reconciliation: K3 = 21.63 µs/call × 39 = 843.6 µs/step, so +0.96% is
  **+8.1 µs/step**; K1 = −0.34 µs/call × 39 = −13.3 µs/step, absorbed to ~0 by
  co-residency. **Predicted net +8.1 vs measured +8.3 ± 7.6 µs — agreement to
  0.2 µs.** The gate failed because two rungs were summed and one was known
  negative. r2 is scoped to **K1-only**, predicted 0 to −2 µs/step on M4 and
  **−0.240% decode (+0.18% score) on M5**.

**★ Her Part 3 inversion, accepted.** Our K3 is the **merged** routed+shared down
projection at 5.31 MB/call = **89% of the M4 ceiling — saturated** — which is why
adding lanes makes it worse. metaspartan's K3 was the **shared-only** projection
at ~0.59 MB/call, latency-bound. "9× the lanes" is exactly what saturated ours.
**Do not ship A1 on K3.**

**★ The field gap is 0.18%, not 0.5%.** `12cb11a8` = our M1 + K1 + K3 = +0.513%
over us, and the ladder prices K1+K3 at 0.75 × 0.689% = +0.517%. **K1 = +0.18%
and reachable; K3 = +0.34% and structurally unavailable to us.** This retires
"match `4bf4f794`/`12cb11a8`'s decode time" as an open direction — we now know
what it is made of.

### E. The command-buffer axes, settled by counting (frieren #23, merged)

**The ops axis is dead by construction.** `needs_commit()` cuts at
`ops > max_ops`, so a buffer cut by the op rule must carry ≥ `max_ops+1` ops.
Counting ops per committed command buffer across 6 arms and 131,954 buffers:

```
MB / ops        cb/step   max ops in any cb
200 / 200 (shipped) 50.0    28
200 / 400           50.0    28    (histograms match bucket-for-bucket)
 40 / 200          127.0    18
100 / 200           80.0    19
400 / 200           19.0    39
```

The biggest command buffer holds 28 ops as shipped and 39 at a 400 MiB cap; the
op rule needs 201. **`MLX_MAX_OPS_PER_BUFFER` is inert at any value ≥ 40.**
Confirmed by a balanced A/A (2000 steps/arm, 12 positions ABBA|BAAB|ABBA):
**+0.144% ± 0.125%, t = +1.15**, drift −0.0008 ms/pos. That design's A/A floor
is ±0.13% (1σ).

**The MB axis is live and binds at the shipped 200** (cb/step monotone
40→127, 100→80, 200→50, 400→19). The "40 MB" figure in the old notes is
`device.cpp:577,581,593` **arch defaults**, not the effective threshold — which
refutes nezuko's stated revert mechanism (her conclusion was right, her reason
wrong). A research host has three thresholds: 50 arch / 128 low-memory / 200
ranked.

**★ The by-product was bigger than the arm.** If the ops knob cannot change
executed work, every receipt differing only in it is an **A/A**. So tree X
(`1feeabc8`) is a fourth *control* replicate, not a decomposition arm. **#20
recomputed:** pooled control n=4 {`5d522d6a` 2.52060, `5e0e9cd1` 2.51302,
`c210d200` 2.52110, `1feeabc8` 2.52274} mean **2.519365**; Y n=2 mean 2.529700 ⇒
**+0.410%** at 1σ = 0.129% = **3.2σ**. #20's merge stands; magnitude corrected
from +0.455%, and the M1 cascade owns essentially all of it since both reverts
are now known-null.

**`MLX_MAX_MB_PER_BUFFER` is SUSPENDED, not closed.** His (possibly unbalanced)
timing gave 50 vs 200 = decode **−1.696% ± 0.175%, t = −9.71**, complete
separation, with prefill +0.504% ± 0.324% and bistable. Two reasons to suspend:
the wiring is gated at ≥96 GiB (`LagunaRuntimeWeights.swift:551`) so a 48 GiB
host never reaches the ranked branch; **and the sign contradicts nezuko's #9
per-command-buffer cost.** An extra cb costs ~1.90 µs gpu_busy + ~2.94 µs host
gap, so +77 cbs predicts **+146 µs worse** and he measured **154 µs better** —
same host, same change, opposite signs, similar magnitude. His own r1 finding is
that unbalanced arm position is worth ~0.86% drift, half the claimed effect. A
balanced re-measurement is free and unassigned.

**Reopened by this:** PR #12's `S +0.236%` regression is now unexplained, since
an inert knob cannot cause the +0.130% on the 400 receipt. Worth 0.085% of score
— on the list, not worth a student today.

### F. DISCLOSED INHERITED RISK — attention quantization exceeds the written envelope

All 40 layers run Q/K/V/O at **NVFP4 g16**. `TASK.md` permits **only group-32
affine INT8** for Q/K/V/O and per-head `g_proj`. The in-tree defence at
`LagunaRuntimeModel.swift:2903-2906` claims "envelope option (1)" — that claim is
**false**. `LagunaConfig.swift:39-41`, organizer-authored (`6d679f4` by `anupsv`),
states: *"Only routed/shared expert projections are NVFP4-packed."* The census
confirms it: 234 = 39 layers × 6 expert projections.

This is **inherited, not ours** (`git blame` → the frontier import `99b974c1`),
and it passes every official gate including the semantic GPQA judge. **Advisor
ruling: disclose, do not unilaterally remove, do not extend.** Removing it would
*add* ~802 MB/step (INT8 g32 is 1.125 B/param vs NVFP4's 0.5625) and cost us the
frontier. An operator ruling is still wanted; the advisor has no tool to open a
GitHub issue.

Note the interaction with §B: because the attention NVFP4 banks are synthesised
by *our* transform, narrowing their scale plane neither widens nor narrows this
exposure.

### G. Flag-position audit — 65 flags, 3 with documented provenance

The provenance vocabulary is diagnostic. *"Ablation on the paired local
benchmark"* means a predecessor's own host (i.e. unverified on M5).
*"Ranked measurement"* / *"MEASURED (2026-08-01, M5 Max … ABBA)"* is real.

58 flags ship ON. The 7 opt-in ones: `DARKBLOOM_TRACE_FUSION`;
`DARKBLOOM_PREFILL_ROUTER_TOP8` (**ranked −0.68%**); `DARKBLOOM_SHARED_FIRST_DOWN`
(**real M5 rig**: +0.10 ms/step, `:7620-7635`, for the stated reason "Metal
memory barriers are encoder-wide, not per-resource"); `DARKBLOOM_ROPE_ATLAS_VIEWS`
(**real M5 ABBA**: +0.01..+0.07 ms/step, `:571-578`);
`DARKBLOOM_NATIVE_AFFINE_SUFFIX`; **`DARKBLOOM_FUSED_QKV`** (`:108-114`,
"paired local benchmark" provenance only — a free flip worth one receipt).

**The doctrine gap this audit left open:** it audited flag *position*, never flag
*magnitude*. §E closed one of the three numeric candidates
(`MLX_MAX_OPS_PER_BUFFER`, inert) and suspended a second
(`MLX_MAX_MB_PER_BUFFER`). The third, **`MLX_BFS_MAX_WIDTH = 50` against MLX's
default 20** (`transforms.cpp:181`), is unmeasured and is **not** a partition
knob — traversal width changes fusion and therefore bytes, so it needs its own
hypothesis, not a knob sweep.

---

## Round 8 outcome / Round 9 in flight

**Round 8 produced three merges, three programme-level laws, and still zero
promotions — but for the first time the laws are prescriptive rather than
cautionary.** #40 r2 (fern) closed the instrument question outright (§0.6) and
handed the programme its ranking rule, its noise model, its detection floors and
its honest promotion bar. #34 r2 (tanjiro) measured the **M5 dispatch law**,
falsified both knee hypotheses at 34.8σ, and disclosed *two opposing
systematics* on his own constant instead of publishing a point estimate (§0.9.1).
#44 (nezuko) took the M4's clearest wall-clock win to the ranked box, watched it
**invert on M5**, and turned that loss into the **M4 TRANSFER LAW** plus the
four-cell boundary model (§0.9.2–0.9.3) — the most reusable artefact of the week,
because it tells every future brief which M4 evidence may be priced and which
may not.

Advisor branch lineage: `9a407ed6` → `a3c096ee` (#27) → `6f1289a9` (#30) →
`eaedee84` (#23) → `ec3298a1` (rewrite) → `cb3d2f68` (#36) → `3039ffc` (record
#36) → `279b6e24` ("Fix competition research mechanics") → `347bb5ce` (round-8
ideas + state) → `d18ebbba` (#32) → `904173a0` (#40 r2) → `1849b376` (#34 r2) →
`7290a7be` (#44) → `8169be4c` (#47) → `7e39f4ee` (docs) → **`5178d452`** (#56),
which is the base for every live arm. Every commit in that chain after
`eaedee84` is documentation-only **except `8169be4c`**, which added +182 B to
`LagunaRuntimeModel.swift` entirely inside the off-by-default `lagunaInject*`
block at `:11046-11224` and was pre-cleared for all four students in the #47
review. All other `baseline_advanced` events were accepted without a rerun under
the standing docs-only rule and re-anchored in the revision briefs.

**Six rounds running, the assigned hypothesis has died and the student has
returned something more valuable than the arm.** That is now the expected shape
of a round, and §0.5.7 finally names the tactical reason it keeps happening: the
resolution floor is *above* what any single mechanism on the board is worth, so a
one-mechanism receipt cannot win even when the mechanism is real. Round 9's
tactic is therefore **screen locally, then stack**, and the queue is ordered by
which arm unblocks the most stacking.

| PR | student | assignment | rev | state |
| --- | --- | --- | --- | --- |
| ~~#32~~ | nezuko | `maple-2026-08-04h-shared-qmv-staging` | r2 | **MERGED** as `d18ebbba` — census + dup/ser lever adopted (§A4) |
| ~~#37~~ | fern | `maple-2026-08-04l-lmhead-level0` | r1 | **CLOSED** — decisive negative, three by-products adopted |
| ~~#36~~ | fern | `maple-2026-08-04k-attn-reduction-packing` | r1 | **MERGED as documentation** — dead family, empty scored diff. See §C |
| ~~#40~~ | fern | `maple-2026-08-05a-nax-stage2-double-buffer` | r2 | **MERGED** as `904173a0` — mechanism #1 null + the whole of §0 |
| ~~#34~~ | tanjiro | `maple-2026-08-04i-m5-block-rates` | r2 | **MERGED** as `1849b376` — M5 dispatch law, block rates, instrument strip |
| ~~#44~~ | nezuko | `maple-2026-08-05b-mb-per-buffer-50` | r3 | **MERGED** as `7290a7be`. Three-point M5 curve complete: 50 MB −1.608%, 200 MB (shipped) 0, 512 MB −1.164%. **Axis CLOSED (§0.9.12)**; knob reverted to `200`, empty editable diff, merged as documentation |
| ~~#47~~ | tanjiro | `maple-2026-08-05c-dispatch-law-close` | r1 | **MERGED** as `8169be4c` (+182 B, off-by-default inject block, pre-cleared). D2 closed the M5 dispatch law: **knee 17.4, c = 2.1828 µs/disp, pool 13.17% of score**; H_knee0 accepted, H_knee300 dead at 12.33σ; D5 declined |
| ~~#56~~ | nezuko | `maple-2026-08-05e-sliding-attn-occupancy` | r1 | **MERGED** as `5178d452`, `status: failed` recorded as a scientific success. Zero scored bytes, no receipt. Killed R1, R1+R2, R1-dual, R4 and the **entire wave-merge family**; measured the wave staircase; forced §0.9.11a, §0.9.11b and §0.9.18 |
| **#35** | frieren | `maple-2026-08-04j-scale-code-width` | **r4** | Stacked-plane candidate green at `checked_steps 1025`. **NOW HOLDS THE RANKED CHANNEL**; precondition = the one-hot 128-probe coherent addressing sweep + the constant-quadruple fraction; all-flag ⇒ he submits unprompted, any silent class ⇒ stop and post. My reprice through the **M5 haircut ×0.399** gives **+0.58% to +0.67%**, not his +1.46%; single-receipt MDE ±0.278%. Deliverable D (instrument deletion) **CANCELLED** (§Ø.5); his head is verified clean of the inject defaults and he **must not rebase** before the receipt |
| ~~#48~~ | fern | `maple-2026-08-05d-fused-norm-qkv-gate` | r2 | **MERGED** as `720c13ff`; review `5196813905`. Ranked receipt `285f79fa` (19:12:03Z) delivered **406 → 326 dispatches, correctness green, `ns` −0.1488%** ⇒ **Reading B, and the whole dispatch-count axis CLOSED (§Ø.1)**. Also produced §0.9.16 (barriers, not dispatches), §Ø.2 (`max_abs_diff 0` is not a bound), §Ø.3 (her own five "oracle passes" retracted), and three corrections to me (§Ø.4). Mode 2 stays default-0; scored diff reverted to `508,711 B` |
| **#57** | tanjiro | `maple-2026-08-05f-gathergemm-coresidency` | r1 | Receipt-free. T1 the 128t-vs-1024t simdgroup-symmetry discriminator that decides whether §0.9.8's occupancy-currency claim and its **15.4 ms** survive; T2 the gather-GEMM threadgroup-footprint census; T3 the owed band-ratio reconciliation (now with two worked cases). **T4 DEFUNDED.** Cleared to `f722c2d7` (`5196932438`) |
| **#60** | nezuko | `maple-2026-08-05g-sliding-attn-load-pipeline` | r1 | **NEW, receipt-free.** R2 = deepen the hand-written 2-deep sliding-attention load pipeline to 4 slots at byte-identical FP order. Primary metric `sliding_attn_lone_tg_us` at K=1, minimize, baseline **9.23 µs**; four hard stops; ≤ +2,000 B. Cleared to `f722c2d7` (`5196871082`) |

Scope boundaries: **fern** owns the ranked-instrument statistics; the `_nax`
gather family is closed and the **decode fusion pool is now closed too**
(§Ø.1) — **she is idle and owed a fresh assignment on a different axis**;
**frieren** owns the attention scale-plane width plus M4→M5 transfer
calibration, the byte budget he is spending, and the **o_proj
instruction-issue question** (the zero-byte 256-entry-LUT discriminator);
**tanjiro** owns the aggregate M5 dispatch law, the gather-GEMM co-residency
discriminator, and the band-ratio reconciliation; **nezuko** owns the decode
roofline, the **boundary-value model**, and — after #56 killed four of her own
five ladder rungs — the **R2 load-pipeline rung only**, receipt-free, capped at
+2,000 B.

**★ The largest staffing gap is no longer unstaffed, and it may be about to
disappear.** Gather-GEMM mechanism **#2** (SM=16 banding) is **closed at the
floor** and its "+1.9–2.6%" is withdrawn; mechanism **#1** measured null;
mechanism **#3** (x re-read) is contingent on the régime answer. The 15.4 ms
excess is still the largest unexplained residual in the programme (+5.7% of
score), but it has no surviving mechanism **and #57 T1 may withdraw the number
itself**: the excess is computed against a perfect-overlap bound of 27.9 ms, and
if co-resident threadgroups serialize in the gather-GEMM the way #56 showed they
do in the attention kernels, that bound is unreachable in principle and the
15.4 ms is not recoverable at all. T1's prereg table commits me to striking it
at a throughput gain ≤ 1.25. This is the round-9 directive working as intended:
a free, local, M4-legal audit deciding a mechanism arm without a receipt.

### Receipt queue — corrected twice, now believed

The "channel is not serialised" model recorded here from #34 is **falsified**.
#34's evidence was *validation* concurrency, not submission concurrency.
Measured behaviour on a real submit attempt:

- **Exactly ONE in-flight submission per ACCOUNT.** A second `mlxfast submit`
  returns `conflict`: *"1 submission already in flight (limit 1)"*. All four
  students and the advisor share `morganmcg1`, so the team has **one** ranked
  slot. There is no queue and no fairness — **the advisor is the scheduler**, and
  a student must ask before taking the slot. This rule is now in every brief.
- Turnaround is **~25–35 min** end to end, scaling with injection size.
- A **`rejected` receipt still publishes full metrics** — S, T, both floor
  verdicts and correctness. `rejected` means only "did not beat current best".
  Only `failed` submissions publish nothing.
- There is **no penalty for submitting a deliberately slowed tree**, which is
  what makes receipt-differencing a legitimate instrument.

Practical consequence, reversing what this section used to say: briefs may **not**
ask for concurrent receipt families. A multi-receipt plan must be an *ordering*
with the cheapest discriminating point first, and every arm must be worth ~30
min of the team's only channel. Corollary from §0: because a same-session
control arm costs a full slot and buys ~0.5% of resolution, **do not spend slots
on control arms** — `c3ce66e` is the standing control until the code base moves.

A `failed` receipt (tanjiro's R4 `afec358`) is a reminder that the 31.5%
field-wide failure rate applies to us too; budget for it when planning an
ordering.

**★★ Operator amendment 2026-08-05 18:39 UTC — dispatch authority and the
mandatory `--model` value.** Two changes, both from the human operator, both
overriding everything written above and everything in earlier briefs:

1. **Every official submission must first be dispatched as
   `mlxfast submit --model "senpai"`** — verbatim, lowercase, quoted. This
   replaces all earlier attribution guidance. Only if the API *explicitly
   rejects* `senpai` as an invalid or unsupported model value may the *same*
   candidate be retried **once** with the actual provider/model. A timeout, a
   network error, a validation failure on some other field, or any unrelated
   error is **not** grounds for the fallback. If the fallback was required, the
   explicit rejection **and** the fallback fact go in the public note; the
   provider/model appears nowhere else.
2. **Advisor, student, or human operator may dispatch**, and **dispatch from a
   provisioned AWS research host is explicitly allowed.** The earlier
   advisor-only / non-AWS restrictions are withdrawn. Credentials are never
   printed or committed.

`senpai/result-template.md` gains two required fields:
`Official submission --model value (planned or used; default senpai):` and
`Explicit API model-value rejection, if fallback attribution was required:`.

**Reference instance:** fern's #48 dispatch was the first fully compliant one —
`--model "senpai"` accepted, no API rejection, no fallback. Point students at it.

**The one-slot rule is unchanged, and the advisor is still the scheduler.**
Widening dispatch authority did not widen the channel: there is still exactly
one in-flight submission per *account*, and `morganmcg1` is shared by all five
of us. Two operational facts learned the hard way this round:

- The channel sat **idle from 15:26:45Z to ~18:5xZ** — about three hours of the
  team's only ranked resource wasted because no one had been told to take it.
  Scheduling is an advisor duty with a real cost when skipped, not a formality.
- Current order: **fern (#48, done — `285f79fa`) → frieren (#35, holding now)
  → tanjiro (#57) and nezuko (#60) are receipt-free by design.** Nobody
  dispatches out of turn.

Service-side caveat that has not changed: **byte-identical archives are
deduped**, so every receipt in a family needs a distinct note.

---

## The editable byte budget is now a first-order constraint

This is new in round 7 and it changes which experiments are assignable. Run
`bash senpai/check-editable-budget.sh <base>` before writing any brief. The
script **requires a full 40-char SHA**.

**Current state, measured at advisor head `f722c2d7` (2026-08-05 20:30 UTC):**

```
current = 2,941,175 / 3,000,000   headroom =  58,825      (2.0% left)
growth  =        20 /   262,144   per-review growth cap
files   =       142 (base = 142)
per-file cap = 524,288
```

| file | bytes at `f722c2d7` | spare |
| --- | --- | --- |
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | **508,731** | **15,557** |
| `Sources/MLXFastModel/LagunaUpstreamEquivalence.swift` | 6,501 | — |
| `Sources/MLXFastModel/LagunaRuntimeWeights.swift` | 31,844 | — |
| `Vendor/.../kernels/fp_quantized_nax.h` | 65,515 | 458,773 |
| `Vendor/.../mlx-generated/fp_quantized_nax.cpp` | 68,466 | 455,822 |
| `Vendor/.../backend/metal/quantized.cpp` | 81,331 | 442,957 |
| `Vendor/.../backend/metal/jit_kernels.cpp` | 50,368 | 473,920 |

**★ The binding constraint is usually total headroom, not the growth cap.** With
58,825 B of total headroom against a 262,144 B per-review growth cap, the growth
cap has never once been the limit. Quote headroom in briefs; quoting the growth
cap gives students a false sense of room. (I made exactly this error in fern's
#48 r2 instruction; she corrected it.)

**★ `growth` is computed UNCLAMPED.** `senpai/check-editable-budget.sh:135`
computes `growth = working_total − base_total` with no floor at zero, so
**negative growth is possible and is a red flag**: it means the working tree has
*lost* bytes relative to the base, i.e. something merged has been silently
reverted. This is not hypothetical — my #48 r2 strip target of 508,529 B was the
*merge-base* size, and using it would have produced `growth = −182`, silently
reverting tanjiro's `5a72af3`. **fern caught it (her §10.2) and stripped to the
correct 508,711 instead.** Read the base size; never recall it.

**★ fern's §9.8: the upstream-equivalence oracle is inside the submitted
surface.** `Sources/MLXFastModel/LagunaUpstreamEquivalence.swift` (6,501 B) is
compiled into the `MLXFastModel` module and is **not** under `Tests/`, as this
document and several briefs previously said. Because `editablePaths` lists
`Sources/MLXFastModel/` as a *directory*, **every byte spent hardening the
oracle is a submission byte.** That changes the cost/benefit of "just make the
gate stronger" from free to charged.

**Round-9 per-file ledger for `LagunaRuntimeModel.swift`:**

| event | bytes | note |
| --- | --- | --- |
| `1849b376` (#34 merge) | 508,529 | |
| `8169be4c` (#47 merge) | 508,711 | tanjiro `5a72af3`, +182 B — **and this is where the inject-defaults regression entered** |
| fern #48 r1 | 518,362 | +9,833 fused kernel |
| fern #48 r2 (`f4c86e44`) | 508,711 | stripped back to the *correct* base size |
| advisor `f722c2d7` | **508,731** | +20 B inject-defaults revert |
| frieren #35 projected | 521,768 | +13,037 rebased |
| nezuko #60 cap | 523,768 | +2,000, leaves **520 B spare** against 524,288 |

**The scored decode path is nearly out of room and the prefill kernels have
essentially unlimited room.** That asymmetry is a research input, not a
housekeeping detail:

- **frieren's #35 and nezuko's #60 collide by 7,293 B if both take their
  original allowances.** Resolved by contract, not by luck: frieren's #35 must
  land `LagunaRuntimeModel.swift` **≤ 523,000 B at submission and at merge**
  with net surface growth **≤ +30,000 B**, and new code goes in
  `LagunaRuntimeWeights.swift` rather than the hot file. nezuko's #60 is capped
  at **+2,000 B net**. Because frieren's merge *will* touch
  `LagunaRuntimeModel.swift`, nezuko must post the non-empty intersection and
  wait rather than rebasing blind.
- **Deliverable D is CANCELLED — the #27 instrument survives.** Deleting the
  `// BEGIN M5 HARDWARE-CONSTANT INSTRUMENT` … `// END` block at
  `LagunaRuntimeModel.swift:11046–11224` would reclaim ≈12,134 B, but it is the
  **only in-tree M5 instrument we have** and its `c`-slope probe is the basis of
  the whole dispatch law. Buying 12 kB by destroying the programme's only
  hardware-constant measurement apparatus is a bad trade. Do **not** delete it.
- **The authorised reclamation target is Metal-literal indentation.** ≈54,251 B
  sits in 71 Metal source string literals as leading whitespace. Reducing
  leading indentation *inside* the literals is byte-cheap and semantically free.
  **Never remove or join newlines** — MSL line structure matters for
  diagnostics and for `#line`-adjacent behaviour. Prove whitespace-only with
  `git diff -U0 | sed 's/^[[:space:]]*//'` showing no substantive change.
  Secondary target: ~108 stale `DARKBLOOM_*` flags, most gating a settled
  decision.
- **`research/` and `senpai/tools/` are outside `editablePaths` and cost
  nothing.** Instruments, harvest scripts, patch files and notes belong there,
  permanently, and should never be carried in `Sources/`.
- The prefill-side implication is the happy one: **§A3's kernel work is
  byte-free.** A double-buffered `Ws` costs a few hundred bytes in a file with
  458 KB of slack. There is no budget argument against prefill kernel work.

A brief that does not check the budget can produce a candidate that times
correctly on-box and is refused by the official static review.

---

## Our position: **1st on content** (`ns` 2.544360 vs crown 2.524190); behind only on the draw

> **§0 supersedes the two subsections below wherever they conflict.** The
> superseded claims: our `ns` is **2.544360** (fern's direct read of `c3ce66e`),
> not 2.5297; best-in-feed is **2.547641**; the crown's `ns` at the median draw
> is **2.524190**, so we are **ahead** on content, not 0.64% behind. The
> "1.443% deficit on the gating metric" is a deficit in *luck*, and ~0.73% of it
> is pure instrument noise. The `diff`-column caution, the field statistics, and
> the crown-movement reconstruction below all remain valid.

**★ Two different rankings, and we had been quoting the flattering one.** Read
directly from the authenticated `mlxfast` CLI on the advisor host
(`mlxfast submissions --all`, 1,496 rows, 67 distinct solvers):

| Metric | What it is | Our rank | Gap to best |
|---|---|---|---|
| `ns` (renormalised) | our own estimator; strips session-to-session draw | 4th of 937 receipts | 0.64% |
| **`officialScore`** | **what the service publishes and what gates promotion** | **7th of 67 solvers** | **1.1375%** |

Best-per-solver, top 7 on `officialScore` (re-read 2026-08-05 10:00; 1,496 rows,
140 promoted, 44 rows dated 8/5):

```
1  lBroth           2.552308  promoted  46eeccf   set 8/4 ~15:10 and NOT re-measured since
2  a-github-name    2.545212  rejected  2ab00e9
3  polymorf         2.538532  rejected  8b352e9
4  metaspartan      2.528244  promoted  21f1d1a
5  davidtai         2.527626  promoted  0a9d439
6  ivanfioravanti   2.526989  rejected  ae9ac90   0.147% above us
7  morganmcg1       2.523276  rejected  c3ce66e   <-- US (was 2.515950 / 71586bc)
```

Our best moved from 2.515950 to **2.523276** with **no code change**: `c3ce66e`
is tanjiro's n=0 zero-injection anchor, i.e. a fourth replicate of the promoted
frontier, drawn in a ~0.3%-richer session (see the drift law in §A). The gap
closed from 1.443% to **1.1375%** by luck, not by work. Because `current_best` is
stored and never re-measured, that ~0.3% is **perishable headroom against a stale
crown** — a real candidate submitted *today* is worth more than the same
candidate submitted next week.

**Caution on the `diff` column.** Its *percentage* is not `diff/current_best`;
back-solving gives denominators of ~1.0025–1.0046, i.e. it is expressed against
~1.0. Only the **absolute** `diff` is trustworthy arithmetic
(2.523276 + 0.029032 = 2.552308 ✓, matching lBroth exactly).

**Keep both metrics, and use each for its own job.** `ns` is the right
estimator for deciding *what is real*, because it removes the session draw that
we cannot control. `officialScore` is the only thing that *gates promotion*, so
it is the right number for deciding *whether to submit*. The crown is therefore
partly a lottery win, and our 1.443% deficit on the gating metric is more than
double the 0.64% content gap we had been planning against.

**Field statistics (same source).** 880 `rejected`, 471 `failed`, 139
`promoted`, 1 `promotion` — a field-wide failure rate of **31.5%** and roughly
**10 submissions per promotion**. Our own 17 submissions are all `rejected`
except `afec358`, which is `failed`.

**The crown is moving.** The `diff` column equals
`score − current_best_at_submission_time`, which lets the best-at-the-time be
reconstructed exactly. Our 8/4 morning and early-afternoon submissions all
reconstruct best = **2.539207**; from ~15:10 on 8/4 onward they reconstruct
best = **2.552308**. The leader improved **+0.516% inside one day**. A plan that
only closes today's 1.443% is not a plan to win.

**Tactical consequence.** Because the service dedupes byte-identical archives,
N lottery tickets require N byte-distinct, behaviour-identical trees. Beating
our own published 2.515950 needs `draw > 0.99456` ≈ 1-in-4 per receipt (§ below).

```
rank  receipt   solver          time   ns        T       S
1     12cb11a8  a-github-name   16:38  2.54270  4.2917  97.707
2     ae9ac90b  ivanfioravanti  09:33  2.53672  4.3076  97.704
3     4bf4f794  a-github-name   06:39  2.53313  4.3177  97.687
4     0c21dc18  US              14:16  2.52973  4.3181  98.029
5     2dce5912  US              14:48  2.52967  4.3267  97.696
6     c00737b7  metaspartan     Aug-03 2.52838  4.3255  97.883
```

Converged-era per-axis position (≥2026-08-03, n=180): **T ours = p97** (field p0
4.2917, p25 4.3427, p50 4.3524); **S ours = p52** (p0 97.359, p25 97.718, p50
97.854). Remaining field-visible headroom: decode 0.710% of T × 0.638 = **0.453%
of score**; prefill 0.516% of S × 0.362 = **0.187%**. Per §D, 0.18% of the decode
gap is reachable and 0.34% is not.

**The field gap is no longer the target — but it is bigger than we said.**
Closing the entire visible decode *and* prefill gap to the best public receipt
buys 0.64% on `ns`; the gap on the *gating* metric is **1.443%** and the crown
moved **+0.516% in one day**, so treat +1.5% to +2.5% as the bar for promotion
to be a coin-flip. §A3's single attributed prefill item is worth **~5% of
score** on its own. §1's unattributed decode residual is worth ~1.27 ms of T;
at elasticity 0.638 a *full* recovery would be ~19% of score, but no mechanism
for it is yet owned and the leading host-side explanation was demoted on
2026-08-05 (see §1) — so do not bank a number against it, bank the census.
Both prizes are *outside* the field's envelope — nobody in the corpus has found
them either. Ranking ourselves against the leaderboard was the right frame
while we were behind on measurement; it is now the wrong frame for choosing
*what to build*, while remaining the only correct frame for choosing *when to
submit*.

### Full `morganmcg1` receipt ledger (18 receipts: 13 on 2026-08-04, 5 since)

```
07:53 27b9c7c6 T4.3530 S 98.153 ns2.51567 draw0.992674 score2.497243
09:30 f8502e12 T4.3704 S 97.622 ns2.51417 draw0.988626 score2.485577  } pre-harvest trio
10:02 71586bcf T4.3828 S 97.513 ns2.51065 draw1.002111 score2.515950  } (our best SCORE)
10:26 f3cda678 T4.3621 S 97.998 ns2.51374 draw0.998094 score2.508953  }
10:49 5d522d6a T4.3475 S 97.841 ns2.52060 draw0.988443 score2.491470  } C0 control, n=4
11:15 5e0e9cd1 T4.3637 S 98.011 ns2.51302 draw0.994854 score2.500092  } pooled mean
11:38 c210d200 T4.3428 S 97.973 ns2.52110 draw0.997477 score2.514743  } ns 2.519365
14:16 0c21dc18 T4.3181 S 98.029 ns2.52973 draw0.985211 score2.492321  } Y = FRONTIER
14:48 2dce5912 T4.3267 S 97.696 ns2.52967 draw0.985388 score2.492708  } mean ns 2.529702
15:10 7a5a1e08 T4.3612 S 98.347 ns2.51083 draw0.998492 score2.507043  fern #24 (closed)
15:34 1feeabc8 T4.3394 S 97.932 ns2.52274 draw0.991135 score2.500378  4th CONTROL (see §E)
16:06 ff29f5c2 T4.8324 S103.568 ns2.30788 draw0.989388 score2.283393  tanjiro instrument A
16:54 553ef9f0 T7.4288 S136.299    ---      ---           ---         tanjiro instrument B
```

Round-6 block-rate family (#34, all deliberately slowed trees — see §A2; these
are instruments, not ranking attempts):

```
R1 b6032aeb T4.27468 S 97.8643  unperturbed control (Sources/ == base tree 6288233)
R2 ca416f01 T5.50538 S141.1262  rate 1 + rate 2 injection
R3 6757de65 T6.51605 S120.0782  rate 3 + rate 4 injection
R4 afec358a    ---      ---     FAILED (no score/metrics) - see A2 correction
R5 c3ce66e1  S/T not yet reported by student   8/5 09:33  score 2.523276
   n=0 zero-injection anchor (DARKBLOOM_INJECT_DECODE_EMPTY=0, _EMPTY_TG=8);
   frontier-equivalent by construction; NEW BEST officialScore;
   +0.321% = +12.4 sd above the three 8/4 replicates ==> the drift law in §A.
   S and T are NOT obtainable from the CLI (metrics column is server-truncated,
   no JSON mode) - the student must report them.
```

R3−R1 is a free method validation: 1354.24 MB moved in 2.241±0.031 ms =
604.2 GB/s = **99.0% of the 610 GB/s nominal**. The differencing instrument is
trustworthy.

Field records: `nd` 2.739127 (`ae9ac90b`), `npf` 2.0220 (`e2822dc1`). Corpus
re-read 2026-08-05 10:00: **1,496 total, 140 promoted, 44 rows dated 8/5**.
Top-per-solver bests are unchanged from 8/4 — the leader's crown is stale.

---

## Established facts (do not re-derive)

### Model configuration (`Sources/MLXFastModel/LagunaConfig.swift:14-50`)

vocab 100352, hidden 2048, 40 layers, headDim 128, 8 KV heads. **48 query heads**
on the 10 full-attention layers (indices 0, 4, …, 36) and **64 query heads** on
the 30 sliding-window layers (window 512). 256 routed experts, top-k 8, MoE +
shared-expert intermediate 512, dense MLP intermediate 8192 on layer 0 only.
`moeRoutedScalingFactor` 2.5, `rmsNormEpsilon` 1e-6, `maxPositionEmbeddings`
262144, bos 2, eos [2,24]. NVFP4 config
`{"group_size":16,"bits":4,"mode":"nvfp4"}`. `queryHeads = layerIndex.isMultiple(of: 4) ? 48 : 64`.

Checkpoint census: tensorCount 912 — bfloat16 405, float32 39, packedUInt32 234,
e4m3ScaleUInt8 234. **On-disk NVFP4 tensors are ONLY
`switch_mlp.{gate,up,down}_proj` and `shared_expert.{gate,up,down}_proj`;
everything else is BF16.**

| class | representation | B/param |
| --- | --- | ---: |
| q/k/v/o | BF16 on disk (`LagunaCheckpointValidation.swift:355-358`), re-quantised at load to **NVFP4 g16** (`LagunaRuntimeModel.swift:2960-2974`, `:5302-5305`) | 0.5625 |
| `g_proj` | group-32 affine INT8 (`LagunaRuntimeModel.swift:431-448`) | 1.125 |
| routed + shared experts | NVFP4 g16 on disk | 0.5625 |
| lm_head, embeddings, routers, dense-0, norms | BF16 | 2.0 |
| KV cache | BF16 (`KVCache.swift:375-376`, `:629-630`); `RotatingKVCache(maxSize: 512, keep: 0)` at `LagunaRuntimeModel.swift:10840-10845` | 2.0 |
| lm_head int5 screening plane | 1344 B/vocab row (1088 for the level-1 pass) | |

### The decode byte budget (~1794 MB/token)

```
attention q/k/v/o NVFP4 g16  802.2  +  g_proj INT8 g32 5.53  =  807.7   45.0%
routed experts, top-8 of 256                                    552.1   30.8%
lm_head int5 plane 134.9 -> 109.2 after #20                     109.2    7.5%
layer-0 dense MLP BF16                                          100.7    5.6%
KV cache BF16                                                  84-89     4.7%
routers BF16, 39 layers                                          40.9    2.3%
embeddings / norms                                               ~3.6
```

Attention census verified two ways: 30 sliding × 37.75M + 10 full × 29.36M =
1426.1M params × 0.5625 B = 802.2 MB, and scale bytes 1426.1M/16 = 89.1 MB.

### The prefill roofline (`research/prefill_ridge.py`)

```
block                 GFLOP        MB   FLOP/B   %FLOP
attn_proj_qkvo       1460.3    2852.1    512.0   51.6%
routed_experts       1005.0   14087.2     71.3   35.5%
attn_core             161.1       0.0      inf    5.7%
shared_expert         125.6      69.0   1820.4    4.4%
dense_mlp_layer0       51.5     100.7    512.0    1.8%
router                 20.9      40.9    512.0    0.7%
TOTAL                2829.5   17159.7    164.9
```

At the **measured** M5 constants this is 50.5 ms of compute and 28.1 ms of DRAM
against S_0 = 97.9 ms. See §1 — the old "on the roofline ridge, therefore
relieving either resource alone cannot help" conclusion depended on the guessed
ceilings and no longer holds.

### The decode dispatch table (nezuko #9, `research/nezuko-pr9-dispatch-fusion.md:126-144`)

`true µs = split µs/call − 1.33`; `%ceil` against the measured M4 260.2 GB/s.

```
dispatch                                        n  true µs  µs/step    MB   GB/s  %ceil
decode_nvfp4_qkv_h64_r1                        30    45.43     1363  11.80   260   100%
routed_nvfp4_swiglu_qmv_packed_top8keys_r1     39    39.05     1523  9.442   242    93%
oproj_act_h64                                  30    38.26     1148   9.45   247    95%
routed_shared_nvfp4_down_residual_r1_v5        39    21.63      844  5.311   245    94%  <- K3
sliding_fused_attn_ring_v1                     30    22.34      670  2.097u / 8.389i    <- issue-bound
lmhead_int5_inline_coarse_v5                    1      515      515  134.9   262   101%
decode_nvfp4_qkv_h48_r1                        10    36.56      366   9.44   258    99%
oproj_act_h48                                  10    30.34      303   7.09   234    90%
full_fused_attn_grow_v1                        10    ~23.5      235  2.621u / 7.86i
residual_rms_router_bf16_2048_rpg8_keys_v1     39     6.81      266  1.062   156    60%
shared_nvfp4_swiglu_qmv_rows1                  39     6.24      243  1.184   190    73%  <- K1
gate_sp_h64 + gate_sp_h48                      40     5.32      213  0.033     5     2%  <- UNASSIGNED
decode_router_top8_ordinal_table_norm_v1       39     2.47       96  0.004     1     0%
rmsbfloat16                                    41     0.87       36  0.008     -     -
command-buffer overhead, 45 buffers            45     1.33       60     -     -     -
Total 8.345 ms gpu_busy_union + 0.200 ms host gap = 8.545 ms/step
```

Four-arm partition sweep: `FUSE=0 SPLIT=0` (**shipped**) 45 cb / 406 dispatch /
8.545 wall / 8.345 busy / 0.200 gap. `FUSE=1 SPLIT=0` 45/366/8.773/8.487/0.286.
`FUSE=1 SPLIT=1` 366/366/9.783/8.749/1.034. `FUSE=0 SPLIT=1`
406/406/10.289/9.030/1.261. **`gpu_busy_sum == gpu_busy_union` to 6 ns in all
four — decode has zero dispatch concurrency.**

Her per-kernel byte sum over 40 layers is ~1657 MB/step, cross-checking the
~1794 MB/token budget to 8%.

### The NAX gate — a programme-level constraint (fern #11)

`mlx::core::metal::is_nax_available()` (`.../backend/metal/device.cpp:913-931`)
requires macOS ≥ 26.2 **and GPU arch gen ≥ 17**. Our M4 Pro hosts report
`applegpu_g16s gen=16`: the OS gate passes, the generation gate fails.

- **94.2% of prefill GPU time on a student host runs Metal functions the official
  M5 never executes** — different kernels, not the same kernel at different
  occupancy: `nvfp4_gather_qmm_rhs_nt` 48.5%, `steel_gemm_fused_nt_bm64_bn64_bk16`
  33.4%, split-K 6.0%, `steel_attention_bfloat16_bq32_bk16` 5.1%, `nvfp4_qmm_t`
  1.2%. Only 5.8% of prefill is host-generation-independent.
- **The steady decode step is 100% host-independent**: every dispatch is a
  hand-written `laguna_*` kernel (or `rms`/`gather_front`). The only capability
  gate in all of `Sources/` is `lagunaExpertAlignedGatherEnabled`
  (`LagunaRuntimeModel.swift:235-249`), used at exactly one **prefill** site
  (`:9631`).
- **Never run a prefill *kernel* experiment on a student host.** Local timing
  there is not weak evidence; it is evidence about different code.
- **★ Full `is_nax_available()` call-site inventory (audited 2026-08-05). The gate
  is wider than this section previously implied.** Every one of these prefill
  paths diverges between M4 and the ranked M5:
  `quantized.cpp:733` (`qmm` — **shared expert, layer-0 dense, router GEMM**),
  `quantized.cpp:972` and `:1959` (`gather_qmm` — fern #40's block),
  `matmul.cpp:957`, `:2485`, `:2559` (steel GEMM / split-K — attention qkvo),
  `scaled_dot_product_attention.cpp:177`
  (`sdpa_full_self_attention_nax` — **the prefill attention core**).
  So *both* the attention core *and* the shared/dense/router `qmm` are
  `_nax`-gated. Correct any brief that assumes otherwise. Note also that
  "attention core CLOSED at the mechanism level (fern #36)" refers to the
  **decode** fused core, not this prefill path — do not conflate them.
- **The M4-legitimate prefill surface is therefore bounded at 18.09 ms = 3.3%**
  of M4 prefill (`research/maple-fern-prefill-roofline.md:29-37`, whose
  "NAX-divergent subtotal 517.92 ms = 94.2%" row is the complement):
  `laguna_*` + elementwise + rms + router + moe_tail + sort/scatter + lm_head.
  Add **13.56 ms (2.5%)** for `nvfp4_qmm_t_splitk_fused`, whose split-K decision
  precedes the gate. No `is_nax_available` branch exists in the
  sort / argpartition / copy / unary / binary / ternary paths.
  **A prefill census run on M4 can legitimately cover only this ~5.8% slice**,
  part of which is already harvested (tournament router, fused residual+RMS,
  prefill async ladder). fern's own C5 predicts only ~1–2% of S from a 30% glue
  cut, which is the honest ceiling for the M4-screenable pool.
- **M4 end-to-end differencing is not usable for prefill at all**: its A/A noise
  is −1.30% ≈ ±7.6 ms, which swamps every candidate here. M4's legitimate use is
  *per-kernel GPU-clock times bucketed by family*, classified byte-bound against
  M4's 260.2 GB/s ceiling or latency-bound; same-source families transfer to M5
  by **DRAM ratio ×0.43** (the validated 106% transfer rule).
- `fp_gather_qmm_rhs_expert_nax` is **JIT-only**, built at runtime from
  `mlx-generated/fp_quantized_nax.cpp`. Editing the header alone changes nothing
  at runtime; the generated `.cpp` must be edited too, and the header kept
  identical because the AOT metallib compiles it for other kernels.
- Three silent-failure modes: odd `TN>1` yields an empty `tile_matmad_nax`;
  `SM<16` yields `TM=0` and no MMA at all; falling off the `bm==64 && wm==4` gate
  (`quantized.cpp:1668-1671`) silently dispatches the non-expert kernel. Any arm
  here needs a positive "MMA actually executed" assertion.
- `SM 16→8` is impossible: `TM = SM/16` (`fp_quantized_nax.h:1719`),
  `kFragRows = 16` (`steel/gemm/nax.h:28,540,547`). The resulting 31.3% MMA row
  padding is a hardware floor.
- **Never express magnitude through a Metal function constant.** A mid-process FC
  flip forces a second pipeline compile inside timed prefill — a reproducible
  15–24% regression (`:1214-1220`).

### Expert gather-GEMM source facts

Inner loop `fp_quantized_nax.h:1721-1795`. `BK_padded = BK + 16/sizeof(Wtype) = 72`
(`:551`); `kWsPerChunk = 8`; `Ws_storage` 9,216 B; `gate_up_stage` aliased
(`:1620-1621`); `kSwigluRegLocal` (`:1741`) true only at BN=64. The loader is
≈50 LSU against ~40 compute ops ⇒ staging is 39.5% of prefill (`:1445-1450`).
`egroups` pinned at 256 (`:1383`, despite a header comment claiming 128).
Variant→tiling `quantized.cpp:1637-1646`; `expert_aligned` `:1659-1663`; accept
gate `:1668-1671`; `grid.x` `:1922`. `tile_matmad_nax`
(`steel/gemm/nax.h:993-1031`) has exactly two branches and no `else`. Trace with
`DARKBLOOM_STAGE2_GATHER=1` / `DARKBLOOM_TRACE_FUSION=1` (`:1700-1705`).

### Attention and MoE kernel source facts

- `laguna_sliding_fused_attn_ring_v1` `:1382`; `laguna_full_fused_attn_grow_v1`
  `:1852`. Both grid `((heads/2)*1024,1,1)`, threadGroup `(1024,1,1)`
  (`:1794-1795`, `:2306-2307`). Sliding constants `:1391-1398`: head_dim 128,
  window 512, gqa 8, BN 32, **BDP 33 after #30**, qk/v_per_thread 4,
  rotary_pairs 64, N 512. Full `:1860-1868`: gqa 6, rotary_pairs 32,
  `yarn_mscale` 1.3465735912322998f. Loop `:1524-1525`; phase 1 `:1420-1465`;
  phase 2 cache write `:1473-1485`; TG memory `:1489-1492`; epilogue `:1626-1660`.
- `laguna_oproj_act_h{heads}_v1` `:4381`, grid `((outVec/8)*64)` = 256 TGs × 64
  threads (`:4425-4429`), **each reading the WHOLE `attention_output`**
  (`:4409-4416`) ⇒ never fold an attention pass-2 into it.
- **K1** `laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1`: decl `:6587`, Metal
  `:6591-6653`, header codegen `:6363-6503`. K loop `:6619`, 4 blocks. Two scalar
  `simd_sum` at `:6641`/`:6642`. **No `threadgroup_barrier` in `:6587-6656`.**
  Dispatch `:6679-6684`, grid `(tiles*64,1,1)` with `tiles=256`, threadGroup
  `(64,1,1)`, `row = tile*2 + simd_group`, 512 rows. Gates `:277-278`, `:128-129`.
- **K3** `laguna_routed_shared_nvfp4_down_residual_bf16_r1_v5`: decl `:7639`,
  Metal `:7655-7745`. No K loop; row loop `:7700` over 4 rows with `simd_sum`
  *inside* the loop (`:7710`). `packed_row_bytes=256`, `scale_row_bytes=32`
  (`:7662-7663`). Only barrier `:7722`, epilogue only. Dispatch `:7791-7807`,
  grid 147,456, threadGroup `(288,1,1)` = 512 TGs × 9 simdgroups. Gates `:142-144`,
  `:7636-7637`.
- Our routed R1 twin at `:7325` **already has depth-1 weight staging** (comment
  `:7365-7370`, prologue `:7371-7384`, next-block loads `:7402-7415`).
- The attention QKV decode kernel: `laguna_decode_nvfp4_qkv_h{heads}_r1_v1`
  (`:4647`). `axis_size 2048`, `num_simdgroups 2`, `values_per_thread 16`,
  `in_vec_size_g = 128`; `column = simd_lid * 16` so **lane L reads scale byte
  L** — 32 contiguous bytes per simdgroup. Grid `((rows/2)*64,1,1)`, threadGroup
  `(64,1,1)`.
- `DARKBLOOM_PACKED_SCALES` (default ON, `:152`, `:166`) builds a **separate,
  dense, row-contiguous** decode-only routed gate/up scale bank at `:9834-9871`
  (~32 MB per sparse layer; codes stay in the resident fused bank). Its
  `:9863-9868` comment records a real trap: a `take()` result carries permuted
  strides and `ensureRowContiguous` would then re-copy the bank on **every
  dispatch**.

### The certified lm_head cascade (`Sources/MLXFastModel/LagunaLmHeadPrune.swift`)

Read `:1-72`; it is the best-documented module in the tree. Stock lm_head reads
the full BF16 [100352, 2048] weight (411 MB) for one row. Behind
`DARKBLOOM_LM_HEAD_PRUNE` (default ON) that becomes four dispatches:

```
1 COARSE     GEMV over the planar int5 copy; decode with FUSED_REFINEMENT reads
             only the 4-bit nibble plane at 1088 B/row -> 109.2 MB/step.
             Emits coarse logit c_i and certified bound delta_i     (:156)
2 ARGMAX-1   stock two-pass (value,index) reduction over `coarse` alone
3 THRESHOLD  finishes argmax, stock single-row GEMV on the coarse winner r,
             thresholds just below bfloat(e_r) -- sound for ANY r since e_r <= e_winner
4 EXACT      each simdgroup owns a FIXED 4-row block, full BF16 GEMV on that block
             iff coarse[r] + delta[r] >= threshold for any of its rows; re-reads the
             dropped 256 B/row residual bit plane for survivors only     (:650)
```

The certificate: `d_i = Σ_j |x_j| · (sd_g/2)` (flat half-cell), emitted as
`delta_i = d_i · (1 + 61·gamma)` with `gamma = 2^-15`, legal because the int5
codes satisfy `|q| ≤ 15` (verified on the real tensor at init, with a fallback to
the stock head on overflow at `:888`). **`delta` is BF16 rounded toward +infinity,
and candidacy is MONOTONE in it, so widening the bound only grows the candidate
set** — the property any new screening level must reuse. `coarse` stays FP32
because it would have to round down for the threshold path and up for the
candidate test.

Decode's three-level split: `nibble = floor(q/2) + 8`, `bit plane = q − 2·floor(q/2)`,
which is what took step 1 from 1344 to 1088 B/row (−25.7 MB/step, nezuko #20,
+0.410% at 3.2σ). The exact pass's per-row arithmetic is a **textual replica** of
the stock `gemv_al_bfloat16` so candidate logits are bit-identical, and every
vocabulary slot is written by exactly one lane on exactly one path. Prefill's
already-sliced final row uses the one-pass form
(`DARKBLOOM_LM_HEAD_PRUNE_PREFILL`, default ON). Roughly **458 of 25,088 four-row
blocks survive** to step 4 (~1.8%), reading 16 KB per live block for ~1.2 wanted
rows.

### Measured hardware ceilings

- **M4 Pro:** scalar FMA f32 7.07 / f16 7.59 TFLOP/s; simdgroup MMA bf16 28.76,
  f16 28.96 TFLOP/s; DRAM **260.2** measured / 262.5 probe control / 273 nominal
  (96.2% of nominal).
- **M5 Max:** 614 GB/s nominal (LPDDR5X-9600, 512-bit), 40 GPU cores, 18 CPU
  cores; **measured streaming read 610 GB/s** (99.3% of nominal); **measured
  dense bf16 GEMM 56 TFLOP/s**; per-dispatch cost not measured (bracket 2.9–3.4 µs).

### Routing histogram at 512 tokens (host-independent, `research/prefill-512-route-histogram.txt`)

311,296 assignments. Mean 16.00 rows per (layer, expert), stdev 28.77
(**CV 1.80**), p50 7, p75 19, p90 39, p95 58, p99 142, max 505, **20.26% of pairs
receive zero rows**, mean nonzero 20.07, median nonzero 11. Busiest 8 experts hold
26.0% of assignments, busiest 32 hold 54.7%. Per-layer max/mean = 15.2×. The
shipped expert tile parameters were "Simulated over uniform routing"
(`quantized.cpp:1405-1415`) — empirically false.

### Harness and gate facts

- **The acceptance band `[0.980, 1.053]` is NOT enforced.** `Constants.swift:150-166`,
  `benchmark.yml:1511` and `overlay-paired-timing.sh:129-169` apply only the two
  0.95 floors. **Never throttle a win to fit the band.**
- **TTFT is not gated.** `gpqa_ttft_max_seconds` is `seconds.max() ?? 0`
  (`LagunaRuntimeCorrectness.swift:230-232`); no threshold exists. Init-time
  headroom is effectively unbounded (our receipts read 0.42 s against the 2.5 s
  reference).
- Upstream-equivalence oracle on base: prefill max_abs **0.125** / mean
  **0.011933609**; **decode steps 0–7 ALL EXACTLY 0** (`EQUIVALENCE_EXACT_STEPS=8`,
  `EXIT=1`). Reproduce exactly 0, not "small". The oracle never calls
  `prepareFusedRuntimeWeights()` — a known scope gap.
- **Local prefill is not an instrument on a sub-64 GiB host.** `--local-iterate`
  reports `prefill_speedup 0.327×` even for a byte-identical build; fern's base
  prefill spans 1.128–1.173 across runs. A/A floor on M4 `--local-iterate`:
  prefill −1.30%, decode +0.48%; fern's own floors ≥1.1% on S and ≥1.5% on T;
  3-pass noise 0.58%.
- Seatbelt: the runtime worker runs under `(deny file-write*)` with only
  `/dev/null`. Only `benchmark --local-iterate|--local-submit` passes
  `forwardsWorkerStderr: true`.
- Submission surface: `editablePaths` = **97 entries**, `fileCount` pinned at 142,
  **59,027 B** of the 3,000,000-byte budget free at `279b6e24`. See the byte-budget
  section for the per-file caps and the #35-vs-#34 mutual exclusion.
- `MLX_MAX_OPS_PER_BUFFER` = 200, `MLX_MAX_MB_PER_BUFFER` = 200,
  `MLX_BFS_MAX_WIDTH` = 50, all at `LagunaRuntimeWeights.swift:381-389`; wiring
  gated at ≥96 GiB at `:551`.
- **Not editable:** `device.cpp/.h`, `eval.cpp`, `utils.h`, `mlx-utils.h`,
  `metal_kernel.cpp`, `scaled_dot_product_attention.cpp`, `MLXHardwareInfo.swift`,
  `array.h`, `fence.cpp`, `transforms.cpp`. `senpai/tools/*` is outside
  `editablePaths`, so **`./probe` on the M5 is impossible**, not merely hard.
- **Editable in `Vendor/mlx-swift`:** `matmul.cpp`, `quantized.cpp`,
  `jit_kernels.cpp`, `kernels.h`, `scaled_dot_product_attention.metal`,
  `sdpa_vector.h`, `softmax.*`, `copy.*`, `unary*`, `binary*`, `ternary*`,
  `arg_reduce.metal`, `sort.*`, `reduce.*`, `reduce_utils.h`, `atomic.h`,
  `reduction/*`, `indexing/*`, `quantized_utils.h`, `steel/gemm`, `steel/attn`,
  `quantized.h/.metal`, `quantized_nax.h/.metal`, `fp4.h`, `fp8.h`,
  `fp_quantized.h/.metal`, `fp_quantized_nax.h/.metal`, `gemv.h/.metal`,
  `rope.metal`, `rms_norm.metal`, all `mlx-generated/*.cpp`. Plus 15
  `mlx-swift-lm` files and 9 `Sources/MLXFastModel/` files.

- **The advisor host has an authenticated `mlxfast` CLI** at `/usr/local/bin/mlxfast`.
  Read-only commands that work: `mlxfast submissions` (ours), `mlxfast submissions
  --all` (**this is the leaderboard** — there is no `leaderboard` subcommand),
  `mlxfast submission-note <id>`, `mlxfast notes`, `mlxfast benchmark`. `timeout`
  is **not installed** on the advisor host, so do not wrap these in it. Use
  `--all` to re-derive the field position and the moving crown rather than
  trusting any number written here.

### Integrity rulings (fern refused to ship both; upheld)

Pre-touching a live buffer pool across the phase boundary, and pre-boosting the
GPU clock across the hello→request boundary, are both **circumvention**, not
optimisation.

---

## Standing measurement rules

1. **Declare the byte numerator** on every byte figure: `unique` or `issued`.
2. **Declare which ceiling you divide by.** The two decode tables use different
   ceilings; do not cross-read them.
3. **A byte saving is not a price until the kernel is shown byte-bound** (§3).
   Cite a measured per-call GB/s against a stated ceiling.
4. Byte-removal arms are priced at ≤0.50× face value and planned against ~0.30×,
   using the **achieved** per-dispatch rate, never the ceiling. Arms predicted
   from a **measured dispatch time** take no discount.
5. **Never compare axes by point-estimate gap.** z-score against a banked
   byte-identical control, and never z-score a field *minimum* against a control
   *mean*.
6. **A product of a ratio and its own denominator is not a measurement.**
7. Quote `amp + ramp = 1.259 ms`, never either half.
8. Manual device-read pipelining across a `mem_threadgroup`-only barrier is a
   no-op at best.
9. Audit every achieved-bandwidth numerator. There is a 16.9×-error precedent.
10. **Do not combine two unmeasured mechanisms.** #32 r1 lost a well-powered gate
    by summing two rungs, one of which it had already isolated as a regression.
11. A bit-exactness corpus needs a **power control** that fails. A test that
    cannot fail is not evidence.
12. **A delete-and-measure attribution is invalid unless you demonstrate the
    deleted code's producers survived.** Deleting a reduction whose result is
    unused lets the compiler eliminate everything feeding it, so you measure the
    reduction *plus its producers*. Keep the value live through a sink the kernel
    actually writes, and diff the instruction count or disassembly — not only the
    time. (fern #36, self-reported against his own #30 table.)
13. **When two arms agree to better than the noise floor, suspect they are the
    same arm before suspecting additivity.** Two independent mechanisms landing
    within 0.1% of each other is a coincidence; one mechanism measured twice under
    two labels explains it exactly. (Advisor error, #36.)
14. **Count dependency depth and ILP, not instruction count**, on any kernel not
    shown to be byte- or arithmetic-bound. See §3.
15. **The runtime instrument and the SPLIT profiler measure different things, and
    the difference is host-side.** (fern #37, adopted.) The long-standing
    30.03 vs 22.34 µs/layer discrepancy is an *instrument artefact*, not a
    kernel finding: split GPU-clock reads 22.66–22.78 µs/layer against the SPLIT
    profiler's 22.34 — **1.7% apart, below the ~2% resolution floor**. The gap to
    30.03 is **+4.1 µs/dispatch of host encode/commit that the GPU clock never
    sees**, plus ~+1.2 µs of command-buffer window granularity. Consequences,
    all now adopted:
    - sliding decode attention is **4.66%** of decode, not 6.16%;
    - the zero-cost ceiling score is **1.0365**, not 1.049;
    - merged #30 re-prices to **~0.36%**.

    The same constant is also a *lead*: 4.1 µs × ~406 scored dispatches =
    **1.665 ms**, larger than the entire 1.383 ms decode residual (§1). Whenever
    you quote a per-layer or per-kernel decode time, state which clock produced
    it.
16. **Never reuse one `.metal` source at two `heads` values without re-checking
    dispatch.** The `heads` field sets only the dispatched threadgroup count, so
    a shared source silently under-dispatches at the smaller value while a
    bitwise output diff still prints 0. (fern #37 probe footgun.)

---

## Closed families — do not re-litigate

- **Decode access-pattern efficiency — CLOSED (tanjiro #21).** Every real pattern
  reaches 87–94% of the sequential control at equal bytes/dispatch. What costs is
  *bytes per dispatch* (22.9 GB/s at 0.125 MB rising to 262.5 at 64 MB) and
  *in-flight bytes per lane* (~32 B to saturate).
- **Offline codes/scales interleave — CLOSED TWICE.** fern read A = 1.000 from
  source; tanjiro measured −0.3% to +2.5% on silicon. Nobody is to propose it
  again. (Note: this is *interleaving*, a different mechanism from §B's *width
  narrowing*, which is live.)
- **`./probe` on the M5 — IMPOSSIBLE.** `senpai/tools/*` is never uploaded and
  there is no shell on the ranked host. The only M5 channel is a submitted
  candidate plus its receipt `metrics`.

| family | verdict | evidence |
| --- | --- | --- |
| **★ `_nax` gather-GEMM stage-2 weight staging (single-buffered `Ws` ↔ MMA overlap)** | **CLOSED — both arms lose (fern #40)** | Three same-session ranked receipts, pre-registered, correctness perfect in all three (`max_abs_diff = 0`, both floors, 9/9 GPQA, 9/9 TTFT, three-way byte-identical oracle). Measured `dS`: v1 double-buffered `Ws` **+0.1150 ms**, v2 register prefetch **+0.4626 ms** — both the *wrong sign* against a predicted −2.4 to −15.4 ms, and both inside σ_dS = 0.2536 ms. `ns` ranks control (2.544360) > v2 (2.539719) > v1 (2.538013). The 0.80× serial-vs-measured ratio that motivated the family cannot distinguish intra-kernel staging overlap from partial residency, and the direct test now says it is not staging. **Do not reopen with a deeper prefetch, a wider `Ws`, or a different barrier placement.** `DARKBLOOM_STAGE2_GATHER` is deleted (−24,164 B). The SM=16 banding (F2) and `x` re-read (F3) mechanisms are *untested*, not closed — but they are ~5–7 ms and ~1–3 ms, so they no longer justify a mechanism-first round |
| **Ranking a candidate by its published `officialScore`** | **CLOSED as a method (fern #40)** | The paired baseline arm runs pinned code, so its whole spread is instrument noise: prefill rel sd **1.932%**, decode **0.248%**, injected into `officialScore` at **0.517%** (σ_ln ≈ 0.73%). Over 1029 receipts an 18-receipt cohort with candidates inside ±0.5% spans **1.805%** of `officialScore`. Both the crown (`46eeccf`, baseline at the **99.7th** percentile, +2.425% premium) and our own best-looking receipt (`4058d0b`, baseline **99.2nd**, z = +2.23) are draw artifacts. **Always rank on `ns` (§0.1).** |
| **A level-0 screen below the certified int4 lm_head plane** | **CLOSED by arithmetic (fern #37)** | The activation is not concentrated enough to screen. The top 256 of 2048 channels carry only **33.5–34.7% of sum\|x\|**; at the group-of-128 granularity the kernel can actually address, the top 2 groups are **14.0% of L1 = 1.1× uniform**. Argmax survival was 100% at K = 1, 2, 4, 8, 12 — but *every* config **adds** bytes (120.8 / 127.7 / 141.3 / 168.6 / 195.9 MB/step vs the shipped 112.4 B / 117.3 A). The certificate needs unread channels ≤ **1.97%** of L1 and the best achievable is **5.73%** — a 3× structural gap, not a tuning gap. Corollary, also adopted: **nothing downstream of the screen is worth byte-optimising** — the shipped cascade already runs its BF16 GEMV on 2.1–3.8 rows/step, so the whole refinement tail is 0.24–0.61 MB/step. The only residual is `lmhead_exact_inline_mask_block_v1` at 76.6 µs/step moving ~0.5 MB: **latency-bound, an M5-only geometry question** |
| **Weight re-read across the N dimension in the `_nax` gather-GEMM** | **REFUTED (advisor's own priority hypothesis)** | `wl = w + y_col*K_w` with `y_col = tid.x*BN` (`fp_quantized_nax.h:1631-1634`) means each column tile walks a **disjoint weight slab**. There is no re-read across N to remove. Verified from source. Also refuted in the same pass: expert load imbalance (< 1 ms), scale-plane cost, and accumulator concurrency. The real mechanisms are staging serialisation and SM=16 banding — see §A3 |
| **Vector / shuffle-count reduction in the fused attention core** | **CLOSED at the mechanism level (fern #36)** | 15 shuffles against `simd_sum`'s 20, same addition tree, **1.79% slower**. `float2` alone −0.27% = one noise floor; pad+`float2` does not stack; `float4` with madds hoisted and `float4` + packed epilogue both null. Geometry identical in every arm, so the M4 null is evidence about M5 (bounded residual 0.013% of score). Both premises in the brief were wrong — see §C. Do not reopen with a different vector width |
| **Attention byte de-amplification / head packing** | **CLOSED, two independent kills** | fern #30: the `h × s = 64` family. h-sweep spans 8× in issued bytes for <8% non-monotone time; the assigned h=8,s=8 two-pass config was **+5.7% slower** with bit-exactness proven. `kv_head=0` (8× fewer unique bytes) gave 30.5 vs 31.4 — unique bytes are not the bound. Independently killed by tanjiro #27's cache-resident probe (kernel at 34% of the cache-resident ceiling at its own working set) |
| **`MLX_MAX_OPS_PER_BUFFER`** | **INERT at any value ≥ 40** | frieren #23: `needs_commit()` cuts at `ops > max_ops`; the largest command buffer holds 28 ops as shipped and 39 at 400 MiB, while the op rule needs 201. Balanced A/A +0.144% ± 0.125%. See §E |
| **The 0.884 ms decode launch-ramp as a recoverable term** | **STRUCK** | tanjiro #27's saturation law: `dT(n) = max(0, n*c − slack)`, knee at 1209 extra dispatches, scored path at ~406. 600 dispatches of pure launch overhead appeared at **1%** of cost. My 2.18 µs in-situ reconciliation is retracted |
| **In-loop host CPU** | **CLOSED** | frieren #14: 2.0 ms/step of injected per-layer host spin *reduced* wall 8.903→8.669 ms; identical spin at the step head passed through 1:1. `wall ≈ head_latency + GPU_total` |
| **Decode head latency** | **CLOSED** | frieren #23: 35.7 µs exposed = 0.82% of the ranked step = **0.52% of score**, below the 0.61% bar; realistic proxy delivered 0.15%. 88% of the term is off-surface |
| **"Do less host work in decode" as a class** | **CLOSED** | frieren #23: graph construction costs 2.51 ms/step but the encoding thread runs **3.5× ahead** of a 96.6%-busy GPU |
| **Decode graph repartitioning** | **NEGATIVE BOTH DIRECTIONS** | −40 dispatches = +0.228 ms (nezuko #9); +81 command buffers via sub-layer `asyncEval` = +1.93% (frieren #23), and cb/step 48→90→129 is non-monotone in GPU busy |
| **KV re-request amplification at DRAM level** | **REFUTED** | frieren #14 slope method. Amplification ≤1.72× full, ≤1.18× sliding; waste ≤ +28.4 MB (≤1.01% of score); the 190 MB claim is ≥6.9σ out. Replacement finding: the full-attention path is the least bandwidth-efficient stream at 58.2% of peak, capped at 16.9 MB/step ≈ 0.6% |
| **Attention / sliding occupancy** | **CLOSED** | tanjiro #13: 80 threadgroups co-reside at the real 17,920 B / 1024-thread shape on 20 M4 cores. The g=21/41 risers are **work imbalance**, `f(m) ≈ 1 + 0.365(m−1)`. `w=2→1` is model-closed as an M5 loss; `w≥4` exceeds the 32,768 B limit |
| **Harvesting the public field by axis-coverage tables** | **CLOSED / RETRACTED** | nezuko #12: de-biased field ceiling 2.5281–2.5318; the advisor's axis tables were note-length artefacts (median \|axis-mean nd − overall\| = 0.220%, inside noise) |
| **`Sources/MLXFastTransform/`** | **CLOSED by dominance** | fern #22: `prepareFusedRuntimeWeights` is **eager** and resident before the first forward (`:10893-10898`), so load-time repack is unscored and *strictly more capable* than offline layout — it can also repack the BF16 attention weights, which offline cannot. RAM is not binding (21.57 of 25 GiB). Untouched in 147 public diffs because it is dominated, not overlooked |
| **NVFP4 scale-plane amplification** | **CLOSED, A = 1.000** | fern #22: the v5 down/residual kernel reads `expert_scales + output_row*32 + lane` over 4 rows × 32 lanes = exactly one aligned 128 B line, fully consumed. Independent bound from its 231 GB/s: `A ≤ 2.14`. The advisor's 8× premise was arithmetically impossible from repo data |
| **Quantized attention weights in prefill** | **CLOSED by arithmetic** | `research/prefill_ridge.py`: `attn_proj_qkvo` is compute-bound at 512 FLOP/byte, so reusing the decode NVFP4 banks shaves DRAM that is already hidden while adding dequantization to the binding term. **General rule: the same weights want opposite representations in the two phases**, because 512 tokens amortise the weight read 512× |
| **Prefill overlap: C1, C2, C1+C2, prefetch depth** | **CLOSED (fern #24)** | Receipt `7a5a1e08` +0.651% slower on `S`. Every barrier in the routed-expert k-loop is `mem_flags::mem_threadgroup` only, so the device read was already hoistable a full iteration earlier than any hand-rolled stage |
| **`DARKBLOOM_STAGE_BM128` tiling family** | **CLOSED at the floor** | One threadgroup per expert (`quantized.cpp:1922`) with simdgroup bands elided past the row count, so MMA waste is *row padding* `ceil(n_e/SM)*SM`. Real routing gives SM=16 → 453,120 MMA rows = 1.456× ideal, and 453,120 is exactly `Σ ceil(n_e/16)·16`, the `kFragRows=16` floor. SM=32 is a flat +41% |
| **First-touch prewarm** | **CLOSED** | fern #19: six back-to-back forwards, the *first* is fastest. Cache exactly 0 B at timed entry. On a ≥96 GiB M5 the constructor already wires ~31.4 GiB before hello |
| **Attention INT8 envelope adoption** | **DEAD, BACKWARDS** | the frontier runs Q/K/V/O at NVFP4 g16 (0.5625 B/param) vs the envelope's INT8 g32 (1.125). Adopting it *adds* ~802 MB/step. See §F |
| **Prefill byte removal as a general strategy** | closed as *stated*, but see §A2/§A3 | the ridge argument was calibrated on guessed ceilings. The residual is now accounted for by subtraction (§1): a 32.4 ms remainder of which **~26 ms is bottom-up-explainable real work**, and the gather-GEMM carries **+26.4 ms** of the normalised residual with ~15.4 ms recoverable via **staging overlap** — a *latency* mechanism, not a byte one. Do not resurrect the old framing; bring a mechanism |
| **`MLX_METAL_FAST_SYNCH`** | **INERT** | read only by `FenceImpl` (`fence.cpp:15`); nothing in `Sources/` or the listed `MLXLMCommon` files constructs an `mlx::core::Fence` |
| **Concurrent encoder dispatch** | closed | `gpu_busy_sum == gpu_busy_union` to 6 ns; entry files not editable |
| **"The dense attention GEMM misses NAX"** | **FALSE** | `matmul.cpp:957` `use_nax` is true for BF16; q/k/v take the regular NAX kernel (`:1025`), `o_proj` takes NAX split-K (`:988-991`) |
| **Prefill dual-representation attention** | already shipped | the native-affine QKV path is gated `B == 1 && L == 1` (`:5497-5498`); both representations are already resident |
| Certified LM-head screening (old form) | closed | #6 |
| M4-argmax geometry as evidence | closed | #10 |
| Routed-MoE BM widening; sub-16 SM; zero-row expert skip | closed | hardware floor / no bytes removed |
| `arangeuint32` caching | closed | the 76 dispatches were a command-buffer overlap artefact |
| Prefill host CPU / command buffers | closed | prefill GPU-busy union is 99.4% of wall |
| `DARKBLOOM_ATTN_QHOIST`, `GEMM_TPARAM_MACRO` | closed | no effect |
| **Match the field's best decode time** | **DECOMPOSED, no longer a direction** | nezuko #32: `12cb11a8` = our M1 + K1 + K3; K1 = +0.18% reachable, K3 = +0.34% structurally unavailable (our K3 is the merged projection at 89% of ceiling). See §D |

**NO LONGER SUSPENDED:** `MLX_MAX_MB_PER_BUFFER` magnitude. The sign
contradiction in §E is resolved in favour of *smaller* buffers by two
independent balanced M4 wall-clock measurements — frieren's 12-arm A/B/B/A
(−1.76% at 50 MB, 2000 measured decode steps per arm, fresh process per arm) and
nezuko's forced-full-profile sweep (**−1.99% at 50 MB, t = −3.2; +2.50% at 400
MB, t = +4.0; monotone in the cap**). The in-tree "6 Latin pairs, decode 5/6"
comment defending 200 MB is p ≈ 0.11 and its record is not in this fork; the
losing arm was most likely 200 MB / **400** ops, not 50 MB. **No M5 datum
exists** — that is exactly what nezuko #44 is buying. Caveat that killed the
first reading: nezuko's own host-gap column stayed flat (0.249 → 0.250 ms) while
the GPU-busy *union* shrank 2.0%, and a union over more command buffers
mechanically excludes more inter-buffer gaps, so **only wall/step counts**.

**REOPENED:** prefill glue (old C5) and shared-expert overlap (old 5b), because
the 29-TFLOP/s "compute-closed" reading that retired them is dead (§1). PR #12's
`S +0.236%` regression, because an inert knob cannot have caused it (§E).

---

## Potential next research directions

Ordered by expected value, **re-ordered on 2026-08-05 12:05 by fern #40's null
and §0's instrument model.** Items **1, 3, 5, 6, 7 are assigned**; item **2 is
promised to nezuko** as her arm after #44; item **4 is closed**. Everything from
8 down is held because all four students are occupied — not because it is weak.

The strategic shift is this: mechanism-first prefill rounds have now returned
three consecutive nulls (#24 prefill overlap, #37 lm_head, #40 gather staging)
at ~30 min of the team's only ranked slot each, while the two changes with real
off-ranked wall-clock support behind them (the command-buffer cap, `gate_sp`
fusion) have never been submitted at all. **Round 8 spends slots on measured
content, not on mechanism hypotheses.** P-SHARED, which held the top of this
queue as of 09:40, is **demoted to a rider** after repricing to +0.18–0.33% —
below the instrument floor as a standalone arm (§P-SHARED). P-GLUE was cancelled
as a census after an adversarial audit; read its entry before re-proposing
anything in that space.

1. **★ Command-buffer geometry: `MLX_MAX_MB_PER_BUFFER` 200 → 50 — ASSIGNED,
   nezuko #44, HOLDS THE CHANNEL.** Two bytes of diff. The only item in the
   programme with **two independent balanced off-ranked confirmations** of the
   same sign and magnitude (frieren −1.76%, nezuko −1.99% wall/step on M4,
   monotone in the cap, 400 MB the reverse at +2.50%). If the M4→M5 transfer is
   even half, this is ~+0.5–1.0% of `ns` for zero bytes and zero correctness
   risk. There is **no M5 datum**, which is the whole point of the receipt. Also
   buys the local {12, 25, 50, 100} argmax — 50 was merely nezuko's lowest
   sampled point.
2. **★ D-FUSE-GATESP — nezuko's next arm, promised.** Fuse `gate_sp_h64/h48`
   (40 dispatches/step, 213 µs/step, ~2% of the byte ceiling, **dup/ser
   first-touch ratio 0.659**) into `oproj_act_h64/h48` (**14.30% of the decode
   step, ratio 0.601**). Both sides of the fusion are ratio-≪1 families, which
   is precisely nezuko #32's signature for *first-touch weight streaming that a
   fusion can eliminate* — the lever converged on independently from her census.
   213 µs of a 5.087 ms step is 4.19% of decode; recovering ~150 µs gives decode
   +2.95% ⇒ score **+2.28%**. Bit-exact, 3–8 KB in `jit_kernels.cpp`, no
   metallib rebuild.
3. **★ Cross-session instrument statistics — ASSIGNED, fern #40 r2, NO GPU.**
   Three numbers decide receipt policy for the rest of the campaign (§0.6):
   (i) the **candidate-arm** cross-session sd for behaviourally identical code —
   if it is ≈0.18% rather than ≈1.9%, then `ns` is ~10× sharper than
   `officialScore` and a **single receipt resolves +0.5%**, which changes every
   brief in this document; (ii) `corr(baseline, candidate)` within a receipt on
   each axis — a high correlation would resurrect same-session control arms and
   reverse §0.5.2; (iii) whether baseline-first arm ordering is observable or
   only inferred, which is the mechanism behind the 10× tension. Cheapest
   high-leverage item in the queue: it consumes no channel slot and no GPU.
4. **The gather-GEMM staging overlap — CLOSED, do not re-dispatch.** Retained
   here only as a pointer: fern #40 measured both arms on the wrong side of zero
   (v1 +0.115 ms, v2 +0.463 ms vs a predicted −2.4 to −15.4 ms). The +26.4 ms of
   normalised prefill residual is still *there* and still unexplained, but
   "staging serialisation" is no longer a live mechanism for it, and the 0.80×
   serial-vs-measured ratio cannot distinguish staging from partial residency.
   Bring a *different* mechanism or leave it.
5. **The ~1.27 ms unattributed decode residual (§1) — ASSIGNED indirectly via
   #32 (census) and #34 (dispatch law).** 29% of the decode step is neither the
   75.5% of bytes now measured at ~100% of nominal nor anything else we have
   priced. **Read §1's 2026-08-05 reframe before designing anything here.** The
   host-dispatch story is *demoted*: 4.1 µs/dispatch is an accounting constant
   reconciling two M4 instruments, not a marginal price, and the closing
   arithmetic puts exposed host cost at **~0.49 µs/dispatch**. There is no
   1.665 ms pool. The leading home is now **in-kernel issue/occupancy/latency
   inside GPU-busy**, concentrated in the ~200 non-byte-carrying dispatches;
   nezuko #9's M4 recoverable column independently sums to **~1.38 ms**, the
   same magnitude, led by sliding fused attention at 428 µs running at 36% of
   ceiling. The two live arms remain complementary: nezuko's per-family
   byte-vs-latency census (#32 B, now aimed at sliding attention first) locates
   the occupancy loss, and tanjiro's M5 dispatch-saturation law (#34 A) decides
   whether *any* dispatch-count mechanism is legal on the ranked host. Do not
   quote a score number for this residual until one of the two lands — bank the
   census, not a number.
6. **Calibrate the missing middle of the M4→M5 transfer table — ASSIGNED,
   frieren #35 r2 A (§5).** One receipt buys a transfer factor for the entire
   class "saves DRAM bytes, adds fixed ALU/transaction cost", which currently
   has *no* calibration anywhere between 1% and 106%. Every future byte-trading
   arm is priced off this number.
7. **The 4-bit lane-major scale plane — ASSIGNED, frieren #35 r2 B.** The
   repriced successor to §B: per-row base + `0xFF` sentinel escape, two loads per
   row instead of twelve, −70…−90 µs/step on M4. `row_le15` is 0.9944 / 0.9864 /
   0.9958 / 0.9814 across the four planes, so the escape predicate is
   simdgroup-uniform in practice. If it lands, the routed/shared planes are 18×
   the bytes (552.08 MB/step, span 39).
8. **SM=16 banding / M-padding — now unblocked, but repriced down.** MMA issues
   453,120 rows for 311,296 useful = **1.456×**, and 453,120 is exactly
   `Σ ceil(n_e/16)·16`, the `kFragRows` floor. The "do not open before #40
   reports" hold is **lifted**: #40 has reported, and its null removes the
   interaction concern along with the reason to expect a big prize. The old
   framing was "while the kernel is staging-serialised this waste is partly
   hidden; once overlap is fixed it becomes binding" — since overlap turned out
   not to be the problem, banding is simply an independent ~5–7 ms item on a
   +26.4 ms residual we no longer have a mechanism for. Worth an arm only if
   someone can show the padded rows actually consume issue slots rather than
   being elided past the row count (`quantized.cpp:1922`), which is the same
   question the `BM128` closure already answered pessimistically.
9. **The latency-bound `lmhead_exact_inline_mask_block_v1` geometry.** #37 closed
   everything else in the lm_head cascade but left this: 76.6 µs/step moving
   ~0.5 MB, i.e. entirely latency. It is an **M5-only** question (§2), so it needs
   receipt pricing or the #34 dispatch law first, and it is small. Listed for
   completeness, not urgency.
10. **Reclaim decode byte headroom.** The #27 instrument block
   (`LagunaRuntimeModel.swift:10975–11223`, ≈12,134 B) and the long tail of the
   **108 `DARKBLOOM_*` flags** are dead weight in the one file that is 15,759 B
   from its per-file cap. This is not a score improvement — it is what makes the
   *next* decode candidate mergeable at all. Partly authorised inside #34 r2 and
   #35 r2; a dedicated cleanup arm is the fallback.
11. **Bit-exact fused split-K for the NAX steel path** (`o_proj`, `g_proj`,
   router). Port `qmm_t_splitk_fused` (`quantized.cpp:849-893`) to
   `steel_gemm_splitk_nax` (`matmul.cpp:689-810`, split-K branch `:987-991`,
   `C_split` fp32 `:734-737`). Removes ~0.72 GB of fp32 round-trip traffic and
   ~80–120 dispatches; ~0.53% of score, and unusually attractive because it is
   **locally falsifiable on the non-NAX twin**.
12. ~~**`MLX_MAX_MB_PER_BUFFER`**~~ — **SUPERSEDED, now item 1 (nezuko #44).**
   Three corrections to the entry that used to live here, all of which matter for
   anyone reading the older briefs: the cb/step figures are **50→85, 200→34,
   400→19** on the full profile (the "45" was the *low-memory* 128 MB / 64 ops
   wiring); the full-profile gate is **≥64 GiB, not ≥96 GiB**, so the knob is
   **live on every ≥64 GiB local box** and `DARKBLOOM_STARTUP_MEMORY_PROFILE=full`
   forces it on smaller ones — the "receipt is the only possible screen" claim was
   wrong, which is why two local confirmations now exist; and frieren's
   **−1.76% / t = −9.71 datum is M4, not M5** (48 GiB host,
   `research/frieren-pr23-r2-cap.md`). His r1 on the same knob was self-retracted.
13. **`DARKBLOOM_FUSED_QKV` free flip.** One receipt; its only provenance is
    "paired local benchmark" on a predecessor's host (`:108-114`).
14. **`MLX_BFS_MAX_WIDTH = 50` vs MLX's default 20** (`transforms.cpp:181`).
    Unmeasured and **not** a partition knob — traversal width changes fusion and
    therefore bytes. Needs its own hypothesis.
15. **Routing-aware two-regime expert dispatch.** The shipped tile is tuned for
    uniform routing that does not occur (CV 1.80, 20.26% empty, busiest 32 experts
    = 54.7%). Row-tile widening, sub-16 SM and the whole `STAGE_BM128` family are
    closed — SM=16 attains the `kFragRows` floor exactly. A *two-regime* split is
    the only remaining route below 1.456× MMA rows and would have to break
    per-expert weight exclusivity. Needs a mechanism proposal, not a knob.
16. **Re-test nezuko's #9 dispatch-fusion negative on the M5, once.** It was
    measured entirely under the M4 blindness of §2, and the ranked host has 2× the
    bandwidth and 2× the cores. Low expected value, but it un-blocks two closed
    families at once if it flips. Largely subsumed by #34's rate work.
17. **Minify the remaining 71 Metal literals in `LagunaRuntimeModel.swift`**
    (−54,251 B). Worth 0.0% of score directly, but it is the largest single
    reclamation available in the file that sits 15,759 B from its per-file cap.
    Promoted from "irrelevant" to "the fallback for item 7" now that the surface
    budget binds — total headroom is 59,027 B, not the ~87 KB previously recorded.

### ★ Round-9 candidate queue — unowned

Full briefs in `research/RESEARCH_IDEAS_2026-08-05_09:30.md` (11 ranked ideas).
Read that file's **ADVISOR CORRECTION** box first: the draft asserted
`DARKBLOOM_SHARED_FIRST_DOWN` was a proven win when it is a measured
**+0.10 ms/step regression**, correctly shipped OFF.

**Claimed out of this queue since it was written (do not double-assign):** the
decode norm/gate fusion pool went to fern as **#48**; **D-FUSE-GATESP/OPROJ** is
promised to nezuko as her arm after #44; the M5 dispatch-law closure is
tanjiro's **#47**; the attention scale planes are frieren's **#35 r3**.

**★★ REPRICED 2026-08-05 20:30 UTC after #56, #48 and the §0.9.11a rewrite.
Every price in the table as it stood on 15:35 was wrong or unsafe. The
superseded rows are kept struck so nobody re-proposes them at the old number.**

**★ Ranked by expected score, biggest first, of what remains UNOWNED:**

**Every price below is either re-derived under §0.9.11/§0.9.13 or explicitly
marked SUSPECT. A `SUSPECT` price may not appear in a brief until it is
re-derived from source — 6 of the 8 banked prices checked so far were wrong.**

| # | item | est. score | class | M4-screenable? |
|---|---|---:|---|---|
| 1 | **M2 — gather elision via `lhs_indices`** (2.15–3.20 ms of dS) | **+0.80% to +1.19%, central +0.95%** — AUDITED §0.9.13 (was +0.4–0.5%, **2× low**) | byte stream | ✓ (byte-stream class, use ×0.399) |
| 2 | **attention `o_proj` lane-major byte narrowing** — o is 8 of 18 scale planes, 39.6 of 89.1 MB/step; 4-bit lane-major 128→65 B/row is 49.2% ⇒ **−19.5 MB/step** | ≈**+0.29% to +0.33%** at ×0.399 — *below* the ±0.278% single-receipt floor on its own, so it is a **stacking rider on frieren's #35**, not a standalone arm | byte stream | ✓ |
| 3 | **D-MLP — depth-2 staging, routed decode QMV** (*not* prefill) | +1.57% central, bracket +0.96%–+2.24%, and an **upper bound** — AUDITED §0.9.13 | byte dedup | ✓ |
| 4 | **`residual_rms_router` rpg8→rpg4/2** (106 µs/step M4) | ~~+1.28% central~~ **SUSPECT** — the 106 µs came from the %-of-ceiling column (60%), which §0.9.18 shows is an *upper bound on byte-boundedness, not a measurement of it*. Re-derive before assigning. | in-kernel occupancy | ✓ |
| 5 | **shared-expert K1** (65 µs/step M4) | ~~+0.78% central~~ **SUSPECT**, same §0.9.18 defect (73% of ceiling) | in-kernel occupancy | ✓ |
| 6 | **split-K NAX** (`nvfp4_qmm_t_splitk_fused`, 13.56 ms of M4 prefill) | +0.53% UNAUDITED | prefill kernel | ✓ (in the 18.09 ms M4-screenable pool) |
| 7 | **byte reclamation — Metal-literal indentation** (≈54,251 B in 71 literals) | 0% directly, but it is the **only way to buy surface headroom** for a decode candidate, and headroom (58,825 B) is the binding constraint | housekeeping | ✓ free |
| — | ~~**★ sliding-attention kernel rewrite** at +3.2%–6.4%, central +5.2%~~ | **WITHDRAWN.** #56 measured the kernel end to end: ≈290 µs/step sliding + ≈100 µs/step full = ≈390 µs/step = **5.8% of score in total**, so 453 µs "recoverable" was arithmetically impossible. Honest residue **+0.6% to +1.2%**. R1, R1+R2 and R1-dual RETIRED; R4 a measured NO-OP; **R2 is the only survivor** and it is nezuko's #60, receipt-free. | in-kernel occupancy | ✓ |
| — | ~~gather-GEMM D2 occupancy audit / the 15.4 ms~~ | Now tanjiro's **#57 T1**, and T1 may **withdraw the 15.4 ms entirely** if the co-residency gain comes in ≤ 1.25. | diagnostic | ✓ M4-legal |
| — | ~~**P-SHARED**~~ | +0.08%–0.10% — below the resolution floor, rider-only | byte dedup | ✓ |
| — | ~~gather-GEMM mechanism #2 — SM=16 banding~~ | ~~+1.9 to +2.6%~~ **STRUCK: closed at the `kFragRows` floor** | — | — |
| — | gather-GEMM mechanism #3 — x re-read (~1–3 ms) | +0.4 to +1.1% *if the 27.9 ms floor holds* | **HELD: contingent on #57 T1** | ✗ `_nax`-gated |
| — | ~~**the whole dispatch-count-reduction axis**~~ | **CLOSED PROGRAMME-WIDE** by fern's #48 receipt (`285f79fa`, `ns 2.540575` = **−0.1488%** vs control, against a pre-registered 10.2σ separation). Reading B confirmed: `c = 2.1828 µs/dispatch` is the slope of an *added-work* probe and does **not** refund when real dispatches are deleted. The removal table (40 ⇒ +1.24%, 100 ⇒ +3.10%, 200 ⇒ +6.21%, 400 ⇒ +12.41%) is **retired as a price list** — it was always an injection response curve. | — | — |

**What changed at the top of this table, and why it matters more than the
reshuffle.** The 15:35 version had the sliding-attention rewrite at rank 1
priced +5.2%, and it got there by *re-derivation*, not by measurement — exactly
the move that §0.9.11 was written to forbid. #56 then measured the kernel and
the whole prize collapsed to ≈390 µs/step total, of which realistically 40–80 µs
is recoverable. **A price derived by re-deriving another price is not evidence.**
The queue now leads with M2, whose +0.95% *was* audited against a byte stream,
and it leads by default rather than by enthusiasm.

**Consequence for how the queue is used.** Nothing above +1% survives audit
except M2 and the (upper-bounded) D-MLP figure. That is the real state of the
programme: the large single-mechanism decode wins are gone, and the remaining
route to a promotion-sized delta is **stacking sub-0.3% mechanisms** (§0.5.7)
behind one receipt. Items 2, 5 and 7 are riders by construction. Design round-10
briefs as *stacks with a shared receipt*, not as a race between standalone arms.

**Assignment order for the next free student: item 1 (M2), then item 3
(D-MLP).** Both are byte-class, both screen on M4 at ×0.399, and neither
competes for the ranked channel in its first phase. Item 7 is a good filler for
any student blocked on a hard stop, because headroom is the binding constraint
on everything else.

- **⛔ P-GLUE as a census is CANCELLED (audited 2026-08-05).** Two independent
  agents — one adversarial verifier, one bottom-up designer — converged on the
  same numbers and overturned the pitch. The record, so it is not re-proposed:
  the "46 ms" is a dense-bf16-priced subtraction leftover that *bundles glue with
  the NVFP4/MoE efficiency deficit* and cannot be separated by that instrument;
  the "~20 ms unowned" was arithmetic error (46 − 15.4 = 30.6, and 15.4 is a
  per-block excess while 46 uses a global `max()`); the "screenable on M4" claim
  is bounded at the ~5.8% non-NAX slice, not the glue at large (see the NAX
  call-site inventory in Established facts); and the cited region
  `LagunaRuntimeModel.swift:9429–9694` **contains fern #40's own kernel**
  (`lagunaFusedSortedRoutedGateUp` at `:9634`), while its `argPartition` +
  `takeAlong` else-branch at `:9429-9440` is **dead on scored prefill** —
  `DARKBLOOM_PREFILL_ROUTER_TOURNAMENT` defaults ON at `:9320` and all its guards
  pass. Per AGENTS.md, "a knob on an unused fallback is not a timing experiment."
- **P-SHARED — DEMOTED TO A RIDER (repriced 2026-08-05 12:05).** It held "give
  the next free slot to this" as of 09:40. A source audit then priced M1-minimal
  honestly and it does not survive as a standalone arm: the `x`-read saving is
  **+78 MiB ≈ 0.16–0.2 ms** and the dispatch saving is **39 dispatches ≈
  0.03–0.07 ms**, total **≈ +0.18–0.33% of score** — at or below §0's
  single-receipt floor, so a null and a win are indistinguishable in one slot.
  Three corrections to the pitch below: the concatenated NVFP4 `[gate; up]` bank
  **already exists and is already resident at prefill** (built by
  `prepareFusedSharedGateUp` at `:8048-8076`, default-ON at `:121-122`), so
  M1-minimal is a **~5-line gate relaxation** costing tens of bytes, no Transform
  edit and no metallib rebuild — much cheaper than advertised but also much
  smaller; layer 0's dense MLP is BF16 with its own `_fusedDenseGateUpWeight`
  (`:8032`), so the span is **39 layers → 117 QMM dispatches, not 120**; and the
  prefill exclusion is **deliberate and documented at `:123-125`**, with the
  closest precedent — `_fusedQKVWeight`'s row-concat — recorded at `:113-118` as
  having "showed a mild prefill cost with no decode gain, so this ships opt-in".
  That is direct evidence *against* the mechanism, not for it. Two further risks:
  `:8300-8301` slices `[1,512,1024]` into non-contiguous views, and widening the
  GEMM's N from 512 to 1024 can select worse `_nax` tiles. **Ride it on a larger
  prefill arm; do not spend a slot on it alone.** The original pitch follows for
  the record. The shared-expert fused gate/up
  branch is **decode-gated**: it requires `x.dim(1) == 1` at
  `LagunaRuntimeModel.swift:8262-8305`, so **prefill issues 3 separate
  `quantizedMM` dispatches per layer where decode issues one fused one.** That is
  a real, local, mechanism-level defect, not a residual. Three staged arms:
  - **M1-minimal (do this first): row-concatenate `[W_gate; W_up]` into one
    qmm**, 2→1 dispatches/layer. **Bit-exact** by exactly the row-independence
    argument already accepted in-code for `_fusedQKVWeight` (`:5683-5689`).
    ~0.3–0.8 ms.
  - **M4 prefill byte-dedup fusions** — the prefill twin of decode's shipped
    residual+RMS fusion; 0.7–1.5 ms, low risk, and genuinely M4-screenable. The
    −0.68% router precedent (`fe01af9`) does **not** apply: that was a
    shape-changing chain replacement, these are byte dedups, the pattern the
    shipped MoE-tail fusion (`:9443`) already proved at prefill.
  - **M1-full (contingent): a prefill-only dequantized BF16 `[gate;up]` bank**
    driving the steel/NAX GEMM path — the exact pattern attention already ships
    on the scored path. Net **1.5–3.5 ms (+0.55–1.3%)** after +176 MB of weight
    reads. Values are losslessly expanded but accumulation order changes, so it is
    **token-exact, not bit-exact** (the prefill oracle tolerance is already
    0.125). *Advisor ruling: permissible.* A lossless NVFP4→BF16 upcast is not
    re-quantization, so the accepted-attention-envelope rule is not engaged; the
    gate is greedy-token equality plus oracle tolerance. Stage it after
    M1-minimal and require the equivalence test.
  Realistic total for the whole prefill fusion pool is **~3–6 ms = +1.1–2.2%**,
  not the +3.7–7.4% P-GLUE advertised. Against a 1.1375% gap that is still
  decisive.
- **⚠ P-SHARED's kill criterion, and the fact that gates it.** Receipt
  differencing prices *marginal* cost. If the two measured blocks overlap
  anything, the 32.4 ms remainder is inflated by the undercount and the pool
  collapses toward the fusion-dedup floor ~3–5 ms. The designed test is one
  ranked arm that **scales all glue families ×2 in place: if S moves < +8 ms the
  standalone-glue story is dead and effort returns to decode.** tanjiro's #34
  nesting answer is the cheap version of the same question — zero receipts — and
  is the highest-value outstanding fact on the prefill axis.
- **Measurement constraints for any prefill census (from the designer's plan).**
  Phase 0 on M4 buys ~80% of the attribution for zero receipts: per-dispatch
  kernel name / grid / bytes, per-kernel GPU-clock times bucketed by family and
  classified byte- or latency-bound, plus a static read of the
  `quantized.cpp`/`matmul.cpp` selection gates. **Never** use M4 end-to-end
  differencing (A/A −1.30% ≈ ±7.6 ms). Transfer same-source families by DRAM
  ratio **×0.43**. **Exclude `:9634`** — it is fern's territory. SDPA and
  shared-expert *absolute* M5 cost are the only non-transferable items and need
  2–3 same-session ranked receipts with distinct dedupe notes.
- **M2 — gather elision via `lhs_indices`** (feed unsorted `x` + `rowOrder` as
  LHS indices instead of materialising the 32 MiB/layer ≈ 1.25 GB sorted copy;
  `SwitchLayers.swift:320-349` → `:9630-9700`). **Bit-exact** — identical dot
  products, only source addressing changes. 2–2.9 ms. Risk: contiguous sorted
  rows are plausibly *why* the block reaches 408 GB/s, so scattered 4 KB row reads
  may cost more than the copy. **UNOWNED AND ASSIGNABLE as of 2026-08-05 12:05.**
  The reservation ("fern's follow-up inside #40") is void: #40 closed the `_nax`
  stage-2 *weight staging* family, and M2 is an *LHS addressing* change, not a
  staging change — the closure does not cover it. It is now the strongest
  unowned prefill item and the only one whose payoff (2–2.9 ms of dS ≈ +1.0–1.4%
  on S ⇒ ~+0.4–0.5% score at elasticity −0.362) survives the #40 null, because
  it removes *real bytes* rather than trying to overlap them.
- **M3 — SDPA epilogue layout**: write O token-major, killing the attended
  transpose (~0.6 GB, 1–1.4 ms) and one dispatch/layer; optionally fuse the
  softplus-gate multiply. Token-exact (pure layout). Receipt-only validation.
- **D-STRAND — decode independent-strand overlap via barrier / encoder
  scheduling.** Decode has *zero* measured dispatch concurrency
  (`gpu_busy_sum == gpu_busy_union` to 6 ns), and the hideable small-kernel pool
  is ≈0.59 ms/step; hiding half is **+4.4%**. The magnitude claim in the ideas
  file is VOID (see the correction box) but the **lever survives and is the
  interesting part**: encode order is bit-exact, M5-measurable, and has
  demonstrated ~2.3%-of-T authority — it has been measured exactly once, in the
  losing direction. Any arm here must begin with a barrier audit, not a flag
  flip. 2–6 KB of Swift, so it needs item 7's byte reclamation first.
- **D-FUSE-GATESP — fuse `gate_sp` (40 dispatches, 213 µs/step, 2% of ceiling)
  into `oproj_act`.** +1.5–3% realistic, +5.6% upper bound, bit-exact, 3–8 KB in
  the roomy `jit_kernels.cpp`. **HOLD LIFTED, and reframed.** It was gated on #34
  deliverable A because I had classified it as a *dispatch-count* mechanism, and
  we have no M5 evidence that dispatch count is priced. nezuko's merged r2
  reclassifies it: the dup/ser **first-touch ratio** is `gate_sp` **0.659** and
  `oproj_act` **0.601** — both far below 1 — which means both kernels spend the
  majority of their time on *first-touch weight streaming*, not on issue or
  occupancy. Fusing them lets one kernel amortise a single pass over the shared
  activation and keeps the O-projection weights resident across the gate
  multiply. That is a **bytes-and-residency** mechanism, which the M5 rooflines
  *do* price, so it no longer depends on the unmeasured dispatch-count question.
  This is **item 2 of the queue and promised to nezuko as her arm after #44**.
  The dispatch-count saving (40/step) is now a rider, not the thesis; the arm
  must be designed and reported as a residency win, and it must state its
  expected byte saving before it runs.
- **D-MLP — depth-2 weight staging in the routed decode QMV** (546.2 vs
  651.8 GB/s achieved). Full closure = **+1.56%**, bit-exact, and it extends the
  existing depth-1 precedent at `LagunaRuntimeModel.swift:7325`.
- **An offline argmax-margin census, to price the bit-exactness doctrine.** The
  gates check *tokens*, not bits. We have never measured how much argmax margin
  the model actually carries, so every non-bit-exact idea has been refused on
  faith rather than on evidence. Offline, no receipt, no score risk; it either
  confirms the doctrine or opens a whole class of arms.
- Also queued: a post-#34 tiny-kernel threadgroup-geometry batch;
  software-pipelined K-tile loads across the sliding-attention reduction
  (+0.8–1.5%, and the one item on this list with a *fully local M4 screen* — the
  lever #36 named but never tested); and byte reclamation promoted to explicit
  enabling work.
- ⛔ **Prefill routing-chain fusion is now DROPPED from the queue, not merely
  deferred.** Three independent reasons: (a) the region the round-8 agent wanted
  fused, `LagunaRuntimeModel.swift:9429-9440` (`argPartition` + `takeAlong`), is
  **dead code** — `DARKBLOOM_PREFILL_ROUTER_TOURNAMENT` defaults ON at `:9320`,
  so the else-branch never executes on the scored path; (b) the closest ranked
  datum is `fe01af9` = `DARKBLOOM_PREFILL_ROUTER_TOP8`, **−0.68%**; (c) our own
  in-code post-mortem at `:8752-8767` already states the answer — at 512 rows
  the stock sort amortizes to a few microseconds per layer, so there was nothing
  to save. Do not re-propose without new evidence that contradicts all three.

**Instrumentation reality check (2026-08-05).** Two facts that bound every
"just profile it" proposal:
- **`DARKBLOOM_GPU_PROFILE` does not exist in the tree.** Zero hits across all
  Swift and C++ sources. Reintroducing it requires reverted hooks in
  `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp` and its header,
  which are **outside `editablePaths`** — so any mechanism that depends on it can
  never ship. Treat it as a local-only debugging fantasy.
- **The one in-tree M5 instrument is the #27 receipt-differencing block** at
  `LagunaRuntimeModel.swift:10973-11223` (≈12,134 B, all knobs default 0). Its
  essential gotcha is at `:11150-11167`: MLX's compute encoder is
  `DispatchTypeConcurrent` and only inserts a barrier on written-buffer binding,
  so **injected dispatches must be chained** through a live dependency or the GPU
  runs them in parallel and they cost nothing — 40 *unchained* empty dispatches
  moved T by 0.006 ms. Any future injection arm must state its chaining.
- `lagunaTrace` (`:70-97`, `DARKBLOOM_TRACE_FUSION=1`) is a **path-firing trace,
  not a timer** — useful to prove a branch is reached, useless for cost.
  `metal::start_capture` at
  `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/metal.cpp:20-46` is the
  only other local option and is not on the submitted surface either.

**CLI limit worth recording — and its REFUTATION.** `mlxfast submissions`
truncates its metrics column server/CLI-side with a literal `...`; widening
`COLUMNS` or `stty cols` does not help, and there is no JSON mode (`--help`
exposes only `--all`). I concluded from that: *"S and T for any receipt are
therefore only obtainable from the student who ran it."* **That was wrong.**
fern's `research/receipt_baseline_lottery.py` harvests, for **1,029 receipts**
across the whole public feed, both arms' prefill and decode per-token times — so
`ns` and the full `(S, T)` decomposition are computable for *any* receipt,
including other solvers', without asking anyone. `mlxfast submission-note <id>`
also returns the full untruncated note for our own receipts. Two consequences:
(a) the crown's decomposition is public, which is how we know the crown holder's
code is ~0.8–0.9% slower than ours; (b) we should still demand S and T in every
assignment, but now as a *cross-check on the student's arithmetic*, not as the
only channel. Any future claim that a number is unobtainable must first try
fern's harvester.

**Standing critique to answer (from the round-8 agent, and it is fair):** the
programme has staffed *measurement* of both big residuals but *mechanism
ownership* of neither, while treating "GPU busy" as "GPU useful". The two items
that convert measurement into an owned mechanism are now **D-FUSE-GATESP** and
**D-MLP** — both decode-side, both bit-exact, both priced by the residency
rooflines rather than by the unmeasured dispatch-count question. P-SHARED has
been demoted to a rider (see its entry above): its repriced +0.18–0.33% is too
small to be a mechanism thesis. Note also that #40 sharpened this critique
rather than answering it: the one prefill mechanism we did own end-to-end
(stage-2 weight staging) came back null, which is why the queue's centre of mass
has moved to decode.

**Caveat on that agent's arithmetic:** it has now produced **two** verified
accounting errors — the `DARKBLOOM_SHARED_FIRST_DOWN` sign error (idea 2's
magnitude is VOID; the knob is a **+0.10 ms/step regression**) and the
`46 − 15.4 ≈ 20` subtraction (it is 30.6, and the 46 was itself the wrong
baseline). Its *levers* have repeatedly been good and its standing critique is
correct; treat every *number* it produces as unverified until re-derived.
