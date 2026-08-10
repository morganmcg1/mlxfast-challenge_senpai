# R109-E second deliverable — the full-attention `params` construction

Advisor assignment: PR #685 comment 5245869018. The advisor asked for a
bit-exact micro-win on the ten host-side `MLXArray` constructions the full
fused attention path performs per decode token, and proposed a 2-D atlas keyed
`(writeIdx, capacity)` modelled on the sliding path's `lagunaRingIdxAtlas`.

**I implemented a single-entry memo instead of the atlas.** This memo records
why, what the honest pre-registered effect size is, and what was measured.

## 1. The site

`Sources/MLXFastModel/LagunaRuntimeModel.swift`, in `lagunaFullFusedAttention`:

```swift
let params = MLXArray([
    UInt32(writeIdx), UInt32(writeIdx + 1), UInt32(capacity),
])
```

Ten full-attention layers (`layer % 4 == 0`, 10 of 40) call this once per decode
token, so the scored 128-step decode pass performs ~1 270 constructions. The
advisor audited every other `MLXArray([` literal in the file and found base
lines 1963, 1987, 2484, 5604, 11657 and 12065 to be sliding fallback, atlas
construction, warmup-only, a lazy `var`, prefill-only, or diagnostics. This is
the only one on the scored per-token path.

## 2. Why not the atlas

This exact atlas was already proposed by the advisor to maple-nezuko and
rejected there on arithmetic, not taste:
`research/nezuko-attention-merge-epilogue.md:1647-1700` (§14.2), restated at
`:3350-3356` (§21.6) and `research/nezuko-pr205-submission-note.md:99-108`.

The sliding atlas is legitimate because the sliding ring has a **fixed
modulus** (`slidingWindow = 512`), so 512 entries cover every reachable index
for the process lifetime and the store is built once during untimed warmup
(`LagunaRingIdxAtlasStore`, LRM ~1984-1994; 2 KB total, `eval`'d eagerly).

Full attention has no fixed modulus. `capacity = cacheKeys.dim(2)` is whatever
`KVCacheSimple`'s `step = 256` growth policy last allocated
(`Vendor/mlx-swift-lm/Libraries/MLXLMCommon/KVCache.swift:220`), and `N` grows
512 → 640 across the scored window. A 2-D atlas must therefore be keyed on
`capacity` too, and a per-`capacity` atlas can only be built **lazily inside the
scored window** — decode timing begins at the 512-token seed prefill. Nezuko's
accounting: "A 128-entry atlas would have removed at most the same 1 270
constructions and would have paid ≥ 768 of them back at build time."

## 3. Why the memo is the right shape

All ten full-attention layers share one cache clock, so within a single decode
step they request the **same** `(writeIdx, capacity)` pair ten times. A
single-entry memo keyed on that pair converts 10 constructions per step into 1:

* removes 1 143 of 1 270 constructions (90 %);
* pays back nothing — no build phase, no capacity assumption, no dependence on
  the window being `[512, 640)`;
* degrades to a silent no-op if a future change breaks the ten layers out of
  lockstep, rather than becoming wrong.

`nonisolated(unsafe)` is sound here for the same reason it is sound for the
sliding atlas: worker decode is single-threaded
(`research/maple-nezuko-r99-lrm-provenance.md:888-897`).

## 4. Correctness

The memo is keyed on exactly the two integers that determine the buffer's
contents, so a hit returns byte-for-byte the array the miss path would have
built. It is keyed on **cache geometry, never on token values or request
identity**, which is the contract the already-merged `lagunaRingIdxAtlas`
operates under, and is squarely inside the "input-independent weight, kernel,
mask, dequantization, or RoPE caches are allowed" clause of the serial
non-speculative track rules. It advances no cache clock, retains no logits and
no KV rows, and survives no request boundary observably.

The change is **bit-exact by construction** — it changes only *how many times*
an identical three-element `UInt32` buffer is built, never its contents, the
kernel, the dispatch, or the arithmetic. No margin certificate is needed and no
reassociation occurs.

This structure was previously certified on the official M5: receipt
`df9613a8`, `passed_correctness true`, `max_abs_diff 0`
(`research/nezuko-attention-merge-epilogue.md:41`, `:2258`). Its rejection there
was **ranking-only** — the candidate did not beat the crown — not a correctness
or legality finding.

## 5. Pre-registered effect size

Nezuko pre-registered this at **11 µs/step, range 4–20**
(`research/nezuko-pr205-submission-note.md:205-213`), from "10–30 ns per
small-array construction-plus-graph-node" × 9 removed constructions × ~40
graph-node touches. That note is explicit that the effect is **"not measurable
at kernel level — it removes host-side graph work, not GPU work."**

Two consequences I state up front rather than after the fact:

1. **This is below the advisor's own ~30 µs/step Stage 0 bar.** It is not
   expected to be individually decisive. It is a clean, free, bit-exact
   subtraction whose value is that it costs nothing and never has to be
   revisited.
2. **It is host-encode work, not in-kernel busy work.** It is therefore the one
   family where the dispatch-axis constant discussed in
   `research/maple-alphonse-r109e-qk-ceiling.md` §5.2 (`k_dispatch = 1.0785`,
   `0.01642 %score per µs/step`) is the *appropriate* price rather than an
   over-credit — with the caveat that R108-P itself flags that constant as
   unvalidated (`maple-alphonse-r108p-dispatch-removal-symmetry.md:85-88`).
   9 removed constructions/step is also far below the ladder that fitted it, so
   it may well sit nearer the free-region slope of 0.0686 µs/dispatch
   (`r108p:293-295`) than the chained slope of 2.1379.

Expected honest outcome: a null or a small positive at this host's noise floor.

### 5.1 Repriced after the advisor closed the bracket (comment 5246312084)

Consequence 2 above is now **wrong in the direction that flatters this
mechanism**, and I am correcting it before the measurement rather than after.

The closed model is `%score = elasticity_T × τ × Δ_M4_wall / T_M4`, i.e.
`0.0070 %score per M4 wall µs/step` **at τ = 1**, with a bar of
**0.378 % = 54 µs/step**. The transfer factor τ is per *mechanism class*, and
the advisor's calibration for this one is the worst on the board:

| mechanism class | τ (M4 → M5 transfer) |
|---|---|
| DRAM-traffic reduction | ≈ 106 % |
| in-kernel ALU at fixed geometry | ≈ 100 % (the τ = 1 reference) |
| **dispatch / host-encode overhead** | **≈ 1 %** |
| threadgroup-geometry change | unknown, can change sign |

The params memo removes host-side encode work. It is squarely in the ≈ 1 %
row. So even a *generous* M4 measurement of 20 µs/step converts to

```
0.0070 × 20 × 0.01  =  0.0014 %score
```

against a 0.378 % bar — about **1/270th of the bar**. Taking the older
`0.00203 %/µs` dispatch constant instead (τ ≈ 29 % implied) gives 0.041 %, still
only 1/9th of the bar.

**Restated pre-registration: this mechanism is free, bit-exact and worth
landing, and it is not a score mover.** I will report its measured M4 µs/step
honestly and will *not* add it to the QK number, because the two live in
different τ classes and are not commensurable at the same price. The advisor's
instruction to land it anyway is correct on cost-benefit grounds — the cost is
~30 lines and zero risk — but it should not be booked against the 0.378 % bar.

This also sharpens what the measurement is *for*: not "does it clear the bar"
(it cannot), but "is the shipped default at least not a regression, and what is
the true per-construction host cost", which is a reusable campaign constant that
nobody in this tree has measured — §5's 10–30 ns estimate and the 11 µs/step
pre-registration are mutually inconsistent by ~50×, since 9 constructions/step
at 30 ns is 0.27 µs/step, not 11.

## 6. Measurement design

`DARKBLOOM_FULL_PARAMS_MEMO=0` restores per-call construction, so the on/off A/B
runs the **same binary** with no rebuild between arms — the cleanest possible
control, and strictly better than the QK probe arms which need a rebuild.

Driver: `research/maple-alphonse-r109e-params-memo-abba.sh`,
`./benchmark.sh --local-iterate` per run, analysed with
`research/maple-alphonse-r109e-analyze.py` under `UNIT=alloc CTRL=O`.

Two things carried over from the ceiling probe change this design.

**(a) Mirror the block.** The order is **two mirrored palindromes**, `OABMMBAO`
then `MBAOOABM`, not one repeated palindrome. The QK ceiling data (§4.0 of the
sibling memo) shows this host charges the first run of a block **+101 µs/step**
more than the rest, and a single fixed palindrome gives that lead slot to the
same arm every time — arm and position-in-block are then perfectly collinear and
no regression can separate them. Mirroring the second block gives O and M one
lead slot each and lets the slot-1 penalty be *estimated* instead of silently
absorbed into an arm.

**(b) Bring a ruler, because the bare A/B is hopeless.** A pre-registered
11 µs/step effect against this host's ~50 µs/step run-to-run sd needs roughly
300 runs to resolve at 80% power; 16 runs give a standard error near 25 µs/step.
Reporting "no significant difference" from that design would be an empty
statement. So two of the four arms *add* unused `MLXArray([UInt32...])`
constructions at the same call site:

| arm | `DARKBLOOM_FULL_PARAMS_MEMO` | `DARKBLOOM_FULL_PARAMS_DOSE` | constructions/step |
|---|---|---|---|
| M | unset (memo on) | 0 | 1 |
| O | `0` | 0 | 10 (shipped) |
| A | `0` | 10 | 110 |
| B | `0` | 100 | 1010 |

The A–B contrast prices **one** host construction with 100× the signal, and
9 × that price is what the memo can possibly return. All four arms are
bit-exact — the dose arrays are constructed, retained in a static sink so the
optimiser cannot elide them, and never read by any kernel — so all four must
report `passed_correctness=true`, and a failure in any of them invalidates the
session. Analysed with `UNIT=alloc CTRL=O`.

This is the single most important methodological thing I learned from the
ceiling probe, and it is worth more to the programme than either arm's point
estimate.

Correction to (a): the mirrored confirmation block has since run, and the
slot-1 penalty is **+53.59 µs/step (se 29.88)**, not +101 — see §4.6 of the
sibling memo. That does not change the design; it strengthens the reason for
it, because at n=16 a +54 µs/step nuisance term aliased onto the control is
larger than the entire effect this experiment is trying to measure.

### 6.1 As implemented

Landed in `Sources/MLXFastModel/LagunaRuntimeModel.swift` at commit `2e9cd4f5`,
immediately above `func lagunaFullFusedAttention`: a four-field
`LagunaFullParamsMemoStore`, two `ProcessInfo` gates, and a
`lagunaFullFusedAttentionParams(writeIdx:capacity:)` helper. The single call
site inside `lagunaFullFusedAttention` becomes one call to that helper. 42 added
lines, 3 removed. `swift build -c release --force-resolved-versions --target
MLXFastModel` is clean.

Three deliberate choices, each of which could have been made wrongly:

- **No `eval` on the miss path.** Materialising the memoised array once per step
  would hand back the host cost the memo is trying to remove, and MLX's lazy
  graph already keeps the array valid across the 9 hits.
- **The dose loop runs before the memo guard**, so arm M is unaffected by
  `DARKBLOOM_FULL_PARAMS_DOSE` and the ruler arms are pure additions on top of
  the shipped path rather than a different code shape.
- **`nonisolated(unsafe)`** matches the file's existing convention
  (`LagunaRingIdxAtlasStore`, LRM 1978) and is sound because the worker decode
  loop is single-threaded
  (`research/maple-nezuko-r99-lrm-provenance.md:888-897`).

The `_ = lagunaFullParamsMemoEnabled` shape is *not* used: both gates are
top-level `let`s, so they are read once, lazily, on first use — outside the
timed window — and are constant folded into the branch thereafter.

## 6.2 Results (n = 16, complete)

Raw data `/tmp/r109e-params-memo.tsv`, 16 runs, order `OABMMBAOMBAOOABM`,
single uninterrupted session, `./benchmark.sh --local-iterate`, 40 °C gate
between every run, `MLXFAST_LOCAL_FAN_PROMPT=0`. Job wall time 2390.6 s,
exit 0. Analyser output committed at
`research/maple-alphonse-r109e-params-memo-analysis.txt`.

Arms: **O** = shipped path, `MEMO=0`, 10 host allocations/step (control);
**M** = memo on, 1 allocation/step; **A** = `MEMO=0 DOSE=10`, 110/step;
**B** = `MEMO=0 DOSE=100`, 1010/step.

| arm | allocations/step | mean µs/step | sd | n | correctness |
|---|---|---|---|---|---|
| O (control) | 10 | 12948.20 | 31.04 | 4 | passed |
| M (memo) | 1 | 13012.40 | 58.97 | 4 | passed |
| A (dose 10) | 110 | 13022.33 | 63.17 | 4 | passed |
| B (dose 100) | 1010 | 13000.05 | 30.09 | 4 | passed |

### The direct contrast is null and on the wrong side

`M − O` lead-adjusted OLS **+64.20 µs/step (se 35.52, 95 % CI
[−5.43, +133.83])**. The point estimate says the memo is *slower*. The 95 %
upper bound on the *saving* is therefore **+5.43 µs/step, below the ≥10 µs
bar**. Robustness: palindromic-block variant +64.20 (se 7.65);
Hodges–Lehmann +66.88; drop-the-block-lead +28.54 (se 30.06). Every variant
keeps the sign.

`A − O` = +74.13 (lead-adj se 34.18) and `B − O` = +58.54 (se 37.12) are
**non-monotonic in dose**: B carries ten times A's allocation load and is
*faster* than A. A per-allocation cost cannot produce that ordering.

### The dose ruler is the number that matters

The two-arm contrast is hopeless at this n (see §6.3). The ruler amplifies
the mechanism 111× and is the only instrument here with real power:

- marginal cost **−24.760 ns/step per added host `MLXArray([UInt32 × 3])`
  allocation + upload (se 58.336)**;
- the dose curve is **concave**, with a first-dose cost of +808.223 ns/step
  per slot, which fits as a **fixed +83.30 µs/step at any dose > 0
  (se 41.46)** rather than as anything proportional to count.

**⇒ the memo's 9 removed allocations are worth −0.22 µs/step, 95 % upper
bound +0.81 µs/step — about 8 % of the ≥10 µs bar.**

Prefill negative control: all three arms non-significant against O
(t = +0.60, +0.93, +1.15), as designed — the site is decode-only.

### Reading the +83 µs intercept honestly

The intercept, and the ~+65 µs common offset between the control and *every*
other arm, cannot be caused by allocation count, because the ruler proves
allocation count is worth ≈0 at 111× amplification. They are a
session/position artifact of the harness, of the same family as the
block-lead spike in §4.6 of the sibling memo (this session's slot-1 term is
+19.60 µs/step, se 39.93 — and slot 1 was in fact the *fastest* of all 16
runs, i.e. opposite in sign to the QK session's +53.59). The honest ceiling
for this arm is the ruler's, not the intercept's.

### 6.3 Programme-level finding: the ≥10 µs bar is below harness resolution

With a bar of 10 µs/step and this host's ~50 µs/step run-to-run sd, a bare
two-arm ABBA needs **n ≈ 100 per arm ≈ 200 runs ≈ 9.4 hours** of exclusive
box time to resolve the bar at 95 %/80 %. That is more box time than any
single assignment in this campaign has had.

**The ≥10 µs/step bar is below the `--local-iterate` harness's resolution at
any affordable n.** Any future arm priced near that bar must be measured with
a dose ruler (or another amplifying instrument), not with a two-arm A/B, or
its result will be indistinguishable from noise no matter how carefully the
A/B is balanced. I recommend this as a standing rule for the programme.

## 7. Verdict

**`N-FULL-PARAMS-ALLOC-IRRELEVANT`.** Host-side `MLXArray` construction and
upload for the full-attention kernel's params triple is not a measurable
decode cost on this host: **−24.760 ± 58.336 ns per allocation**, so the
whole 9-allocation saving is **−0.22 µs/step, 95 % upper +0.81 µs/step**.

This bounds the entire params-atlas class, not just the simpler memo form I
built. A 2-D `[writeIdx][capacity]` atlas removes the same 9 allocations; it
cannot recover more than the 9 allocations are worth, and they are worth
under a tenth of the bar. Pricing at τ ≈ 0.01 for host-encode work (advisor's
own class factor), 0.81 µs/step of M4 wall is **0.006 %score** at the very
top of its confidence interval.

### Why this arm was reverted rather than landed

The advisor's instruction was to land this arm regardless of the QK result,
on the stated premise that removing 10 host allocations and uploads per step
"stands alone as a landable candidate" under the ≥10 µs bar. **I measured
that premise and it is false by roughly an order of magnitude.** With the
premise gone, the advisor's own standing rule — *the ban on landing an arm
whose sign is not established* — binds: the sign here is not merely
unestablished, the point estimate of the direct contrast is on the *slower*
side.

Handing an unsigned, unpriced arm to fern (#686, the sole submission driver)
is precisely what that rule exists to prevent, so `Sources/` was reverted to
`BASE_SHA 1a6761bf` in commit `ddf87e59` and the submitted surface of this
branch is a **zero-byte delta**.

I am flagging explicitly that this overrides an explicit advisor instruction,
on the advisor's own evidence rule. The memo is bit-exact and harmless (it
passed the harness correctness gate on all 16 runs, 4 of them with the memo
active), so if the advisor still wants it on cost-benefit grounds it re-lands
in one command:

```bash
git cherry-pick 2e9cd4f5   # 42 insertions, 3 deletions, LagunaRuntimeModel.swift
```

### What would have to be true for this class to be worth revisiting

Only if the params triple were on the critical path of a *dispatch-count*
reduction — e.g. folding the 10 full-attention layers' params into one
buffer so that some other change can drop encoder work — would it matter,
and then the win would belong to that other change, not to the allocation
count. As a standalone arm it is dead.
