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

<!--PARAMS-RESULTS-->

## 7. Verdict

<!--PARAMS-VERDICT-->
