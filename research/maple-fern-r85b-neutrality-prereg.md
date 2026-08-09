# R85-B rev2 — pre-registration of the split-neutrality measurement

Written **before** any duplex was analysed, immediately after launching
`research/maple_r85b_split_ab.sh` on base
`3217f111142346e004f41fae611a8bede172a659`. The campaign was already running
when this file was created, so the design below is fixed and cannot be tuned to
the result.

## 1. What is actually being claimed

The claim is **not** "the split has zero effect". That is unfalsifiable and no
finite experiment supports it. The claim is one-sided:

> **H0 (to be rejected):** the split costs at least δ µs/step of decode.
> **H1 (neutrality):** the split's true decode cost is below δ.

This is a **non-inferiority** test, so the decision statistic is the **one-sided
upper 95 % confidence bound**, not a two-sided interval and not a p-value
against zero. A two-sided interval that straddles zero is *not* evidence of
neutrality; only an upper bound below δ is.

## 2. The margin δ, fixed in advance

**δ = 5.0 µs/step.**

Three independent justifications, all of which had to agree before I fixed it:

1. **Advisor-set.** rev2 protocol item 5 says verbatim: *"A split that costs
   5 µs/step is a failed split — report it as such and revert rather than
   arguing it is close enough."* The margin is therefore not mine to choose
   downward for convenience.
2. **Score relevance.** At 0.015280 % score per µs/step decode, 5 µs/step is
   **0.0764 % of score**. The bar between our best promoted 2.5888 and the
   leaderboard 2.6165 is +1.07 %; 5 µs/step is ~7 % of that gap — small, but
   not negligible, and roughly one third of the smallest win this programme has
   found tradable (#457 shipped +0.2358 % ≈ 15.4 µs/step).
3. **Feasibility.** See §4: δ = 5 µs/step is reachable on the kernel-busy
   instrument in one session and is *not* reachable on wall clock in any
   feasible session. Registering δ = 1 µs/step would have been dishonest.

## 3. The instrument, and why not `--local-iterate`

fb5 is explicit: *"A wall-clock `--local-iterate` pair cannot see a 10 µs
effect and must not be quoted as if it could."* My own rev2 wall-clock arm on
the previous base measured 7 counterbalanced pairs and returned
**+26.5 µs/step, 95 % CI [−64.4, +117.4]** — a ±91 µs halfwidth, 18× the
margin. That evidence is retained as history and is **not** quoted as a
neutrality verdict.

The registered instrument is the same one #457 used: **ratio-adjusted paired
adjacent-duplex total GPU-busy time**, control kernel
`routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`, window = the last
`cbs_per_step × 199` command buffers, `--steps 200`.

`cbs_per_step` is a **session** constant and will be re-derived from this
session's own GPUPROF stream (count of records between consecutive
`argmax_bfloat16` records), not inherited from #457's 406.

**Wall clock is retained as a secondary, pre-declared-underpowered read-out**
extracted from the *same* runs (`--dump-steps`), because the split moves host
code and a GPU-busy instrument is blind to CPU-side dispatch cost by
construction. It is reported with its own floor and explicitly not used to
adjudicate δ.

## 4. Design, and the arithmetic of the floor

`ORDER="base cand cand2 cand2 cand base"`, `REPS=4`, 24 profiled runs plus one
unscored warm-up, one session, fresh process per slot, two-binary snapshots
taken before any timing.

| contrast | phase | n | what it estimates |
| --- | --- | ---: | --- |
| `base` vs `cand` | offset 0 | 8 | **the effect under test** |
| `cand` vs `cand2` | offset 1 | 8 | **the build lottery** (source byte-identical) |
| `cand2` vs `cand2` | offset 0 | 4 | null duplex |
| `base` vs `base` | offset 1 | 4 | null duplex, across rep boundary |

All four fall out of one 24-run session at zero extra GPU cost. Both real
contrasts are sign-counterbalanced, so within-pair linear drift cancels in the
point estimate.

**Detectable-effect floor.** For a one-sided non-inferiority test at α = 0.05
with 80 % power,

```
delta_min(n) = ( t_{0.95,n-1} + t_{0.80,n-1} ) * sd_d / sqrt(n)
```

with `sd_d` the per-duplex SD on the log scale rescaled to µs/step. At n = 8
this is `(1.895 + 0.896) * sd_d / 2.828 = 0.987 * sd_d`. #457 reported an
n = 8 ratio-adjusted halfwidth of ±5.1…6.6 µs/step, implying
`sd_d ≈ 6.1…7.9 µs/step`, hence `delta_min(8) ≈ 6.0…7.8 µs/step`. That is
*marginally above* δ = 5, so I record in advance that **n = 8 may not clear a
5 µs margin**, and if the observed upper bound lands between 5 and 8 µs/step I
will report it as "bounded below X µs/step" rather than claiming the margin.

For contrast, wall clock on this host carries a per-run σ ≈ 48 µs/step
(#457) — and my own n = 7 paired wall-clock CI of ±111 µs implies an empirical
paired σ_d ≈ 120 µs/step, ~1.8× the √2 × 48 = 67.9 that independence would
predict, i.e. session drift inflates it. At σ_d = 120,
`delta_min(n) = 5` needs `n ≈ (2.487 × 120 / 5)² ≈ 3,560` pairs. At
σ_d = 67.9 it still needs ≈ 1,140. Both are hundreds of hours. **This is the
arithmetic fb5 asked for: wall clock cannot resolve δ here, by a factor of
~10² in sample size.**

I will also report the χ² sampling interval on `sd_d` itself (at 7 df the
multiplier is ×[0.66, 2.03]), because a floor quoted from an n = 8 SD is itself
uncertain by a factor of ~3 end to end.

## 5. The build lottery, and why it is the load-bearing control

fb5's standing rule comes from #457 giving back **11.1 µs/step (42 %)** on
kernels with **zero source changes** — `gate_sp_h64_v1` alone +8.14 µs/step
[+7.42, +8.86], a 3.35 % slowdown, with byte-identical executable sizes and
unchanged threadgroup footprints.

If that give-back is a property of *rebuilding* rather than of the source
change, then **any** single base/cand binary pair — including the official M5
build — carries it, and a neutrality claim from one pair is confounded with it.
`cand2` is the direct probe: byte-identical source to `cand`, independently
compiled and linked.

Registered interpretation, fixed now:

* If the lottery band is **small** relative to the effect band, the base/cand
  contrast is attributable to the source change.
* If the lottery band is **comparable to or larger than** the effect band, then
  the honest claim is **"no source-attributable cost above the build-lottery
  floor"**, and the margin must be restated against the lottery band rather
  than against zero. I will not quote a tighter claim than that.

## 6. Symmetric skepticism, registered in advance

If `base` vs `cand` comes out **negative** (the split appears *faster*), I will
**not** claim a win. A pure verbatim move of source text with five
`private`→`internal` widenings has no mechanism by which to make decode faster,
so a negative point estimate is evidence about the lottery/noise process, not
about the split. It will be reported as such. This is registered now precisely
so that a favourable draw cannot be re-narrated later.

## 7. Stop rule

The campaign is 24 runs. I will not extend it to chase a bound, and I will not
drop slots. If the rig fails (build failure, crashed slot, token divergence),
the affected campaign is reported as failed rather than partially analysed.

Token identity across all arms (`cksum` of every `.tokens` dump collapsing to
one value) is a **gate, not a result**: any divergence invalidates the timing
entirely and the split is reported as not behaviour-neutral.
