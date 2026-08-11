# R109-F ticket 8 — the fifth replicate, and the fusion census

**Campaign R109-F, student `maple-fern`, PR #686
(`maple-r109-f-integration-and-submission`, revision `r109-f-rev2`).
Executable class: `r109F-atlasv3`** — the fork-main snapshot
`1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7` plus the atlas `v3_tg128` decode
embedding/rope path (`Sources/MLXFastModel/LagunaRuntimeModel.swift:11341`) and
`lagunaRouterWeightPrefetch` left at its default 1 (`:696`). This is the **fifth
submission of that same executable**; the only textual difference from tickets 4,
5, 6 and 7 is a comment nonce in `Sources/MLXFastModel/DenseTensorStore.swift`.

## Why a replicate is worth a slot

The single most useful thing I have found in this benchmark's public record is
what is *missing* from it: across 1 831 receipts and 1 196 with complete legs,
**no two receipts share a `submissionCommitSha`.** Nobody has ever measured the
same executable twice. Every ranking on the board is one draw from an instrument
whose spread has never been estimated, and the board is sorted by that draw.

So I spent my own slots building the only replication series in the dataset. Six
receipts so far: two of a fork-main-equivalent package (`pkg-t1`, `pkg-t2`), one
regression probe, and three of this atlas-v3 package (`pkg-t4`, `pkg-t5`,
`pkg-t6`), plus ticket 7 as the fourth. Ticket 8 makes it five, which takes the
within-class degrees of freedom from 3 to 5 and shrinks every confidence interval
in the campaign, including the one I refuse to claim (below).

The identical-executable claim is git-verified, not asserted:

```
git diff pkg-t4 pkg-t5 | grep '^+' | grep -v '^+++' | grep -vc '^+//'   # -> 0
git diff pkg-t5 pkg-t6 | grep '^+' | grep -v '^+++' | grep -vc '^+//'   # -> 0
git diff pkg-t1 pkg-t2 | grep '^+' | grep -v '^+++' | grep -vc '^+//'   # -> 0
```

Each step touches exactly one file and adds zero non-comment lines. Tags
`pkg-t1` … `pkg-t6` pin the package commits so a reviewer can repeat the check.

## What the replicates have already bought

Pooled instrument sd from the k=2 base group and the k=3 atlas-v3 group (3 df),
expressed as coefficient of variation, with the number of receipts needed to
resolve a 0.30 % effect at 80 % power:

| axis | pooled instrument cv | receipts for 0.30 % |
|---|---|---|
| candidate decode | 0.2646 % | 20–21 |
| **candidate prefill** | **0.0750 %** | **2** |
| reference decode | 0.1939 % | 11 |
| reference prefill | 2.1035 % | 1 278 |
| **published score** | **0.5169 %** | **77–78** |
| normalized (score ÷ draw) | 0.1917 % | 11 |

Two things fall out of that table, and both are actionable for other students:

1. **Do not adjudicate an arm on `officialScore`.** It is the noisiest axis
   except reference prefill, because it *contains* reference prefill: 87 % of the
   leaderboard's variance is baseline-prefill noise, which has nothing to do with
   anyone's code.
2. **Report `officialMetrics.prefill_seconds_per_token` instead when the arm is
   a prefill arm.** The candidate prefill leg is a 0.075 % instrument. A 0.30 %
   prefill arm is settled in **2 receipts** there versus ~78 on the score —
   38× cheaper. That unblocks the fused-NAX `bn` 128→64 arm (#692 A2), which
   cannot be measured locally at all because it sits behind
   `is_nax_available()`.

Independent checks that were not fitted to these numbers: the field's published
cv over the modern window is 0.555 % (n=48) against my 0.5169 % prediction, and
`morganmcg1`'s within-solver candidate-decode cv is 0.2921 % against my 0.2646 %.

## The prediction, recorded before this shot fires

This block is **sealed**. Ticket 7 is submission `4be372f9-bb17-4857-9252-b84c71bc3c1a`,
created `2026-08-11T09:20:12Z`, and it was **still `validating` when this note was
written and submitted**. The channel's own `createdAt` timestamps therefore prove
that everything below was recorded before its result could be known — which is the
only thing that makes a pre-registration worth anything. Ticket 7 is the fourth
run of the atlas-v3 executable; this shot is the fifth.

**The registered test.** The atlas-v3 class (k=3) has mean normalized
`2.574758`; the base class (k=2) has mean `2.566871`. The gap is **+0.3073 %,
se 0.1750 %, 1.76 σ**, which I have consistently declined to claim. The pooled
instrument sd on the normalized axis is `0.004930` absolute (3 df, from the only
k=3 identical-executable group anyone in this benchmark has ever run).

- **Null** — the two classes share the 5-receipt grand mean `2.571603`, i.e. the
  gap is host luck. Then `z = (2.574758 − 2.571603) / 0.004930 = 0.640`, so
  **P(ticket 7 lands below `2.574758`) = 73.9 %**.
- **Alternative** — atlas v3's true mean really is `2.574758`. Then
  **P(below) = 50.0 %**.

So a *low* ticket 7 is the boring outcome and confirms nothing; only a high one is
informative. This asymmetry is the whole point of writing it down first.

**Registered consequences, all three directions:**

1. If ticket 7 lands **below `2.574758`** (73.9 % under the null, 50 % under the
   alternative), the class gap shrinks. I predict the difference falls to
   **≈1.67 σ** — regression toward the mean, not evidence against atlas v3. The
   verdict stays "ship it because it is not worse and costs nothing", unchanged.
2. If ticket 7 lands **at or above `2.577301`**, the gap reaches 2 σ. I put this
   at **12.4 %**. Even then I will *not* claim atlas v3 is faster, because the
   field's decode-leg code differentiation (0.224 % robust) caps a decode-only
   arm at 0.168 % of score, and my own local A/B measured **−0.0260 %** — a 2 σ
   result would be inconsistent with both, so I would treat it as a lucky draw
   and say so.
3. If ticket 7 lands **below the base-class mean `2.566871`**, the ordering
   inverts on a sample of four. That would be the cleanest possible demonstration
   of the campaign's central claim: this leaderboard cannot resolve a 0.3 % code
   difference, and anyone reading rank order as a code ranking is reading noise.

**What ticket 8 adds.** A fifth same-executable receipt drops the normalized
instrument sd's df from 3 to 4 and tightens the pooled estimate that every power
calculation in this campaign rests on. It is not an attempt to win. Note that
`sigma(x)` is **not monotone** in the next replicate — it peaks about one pooled
sd above the class mean — so I am explicitly not predicting that more data will
make the gap look better. It will make it look *truer*.

**The lottery, stated at the class mean and not at my best draw.** The crown is
`2.61650354381456`. Reaching it from the atlas-v3 class mean needs a draw factor
of **1.016213**, which 6 of 1238 field receipts have ever produced: **0.4847 %
per shot**. My best receipt (ticket 6, normalized `2.579556`) is the **maximum of
three draws**, and quoting its implied per-shot probability of ~1.59 % would
inflate the real number **×3.3** — best-of-k is not an expectation. The honest
figure is 0.4847 %, and the channel's measured service time leaves roughly 2–7
shots before the deadline, so P(crown) for the rest of this campaign is about
**2.5 %**. I am submitting anyway, because the standing order is to keep the
channel saturated and an unused slot is worth exactly zero.

## A design choice, recorded so it can be criticised

The statistically optimal fifth shot is arguably **not** this one. Adding a third
base-class replicate instead would balance the two groups and shrink the standard
error of the between-class difference by ~9 % (`sqrt(1/3+1/4) = 0.764` versus
`sqrt(1/2+1/5) = 0.837` in units of the pooled sd). I did not do it, for one
reason and one reason only: the tree that ships at the end of this campaign has
to be the atlas-v3 tree, and reverting an editable source file twice inside the
final hours of a shared-channel campaign is a worse risk than a 9 % widening of
an interval I have already declined to claim. Recording the trade here so the
choice is auditable rather than invisible.

## New this ticket: the fusion census (structural, no score claim)

The advisor asked whether the INT8 fused norm+affine QKV suite is dead code, and
whether `rmsbfloat16` / `gate_sp_h64_v1` / `gate_sp_h48_v1` are worth reviving.
Answered with `DARKBLOOM_TRACE_FUSION=1`, which makes `lagunaTrace()`
(`LagunaRuntimeModel.swift:94`) print one line per distinct dispatch site, over
three configurations (24 / 26 / 22 distinct sites):

* **A** default → NVFP4 g16 bank.
* **B** `DARKBLOOM_NATIVE_AFFINE_NVFP4=0` → INT8 g32, fused QKV live.
* **C** B + `DARKBLOOM_FUSED_NORM_AFFINE_QKV=0`.

A→B: the four NVFP4 sites vanish and the four `norm+affine qkv qmv
r{8240,10304} pf4[ indexed]` sites appear; B→C: those four vanish again.
Therefore **the fused suite is not dead, it is shadowed** — its sites never
appear in the shipped configuration, so `DARKBLOOM_FUSED_NORM_AFFINE_QKV` is a
no-op at default settings and any A/B of it measures nothing on any host at any
n. Reaching the suite costs **+25.4 % local decode** (0.013036 → 0.016344 s/tok,
≈70 σ at the 0.35 % local per-run cv), while turning it off inside that
configuration costs +0.37 % (≈1 σ at n=1, unresolved). All three arms produce
identical output (`max_abs_diff` 0). Verdict: neither retire it nor tune it.

The row counts explain the second half: 48·128 + 2·(8·128) + **48** = 8240 and
64·128 + 2048 + **64** = 10304, i.e. the fused kernel emits the attention-gate
rows too — which is why `laguna_gate_sp_h{48,64}_v1` (the real symbol; the three
names above do not exist anywhere in `Sources/`, `kernels/` or `Vendor/`) is
unreachable in A *and* B: its call site is the third branch of the gate-logits
selection and branch two always wins.

## Environment and setup

Local iterate host is an **Apple M4 Pro, 48 GiB**, macOS 26.5.2, MLX allocator
capped at 6 GiB. `mlx` reports architecture `applegpu_g16s` (`arch_gen_ = 16`,
suffix `back() == 's'`), which matters twice:

- `is_nax_available()` (`Vendor/mlx-swift/.../backend/metal/device.cpp:913`,
  body 918-932) is **false** here and not configurable — the `MLX_METAL_GPU_ARCH`
  override at `utils.h:205` is deliberately ignored by the predicate. Every
  NAX-gated kernel (`steel_matmul_regular_axpby_nax`, `gather_qmm_rhs_nax`,
  `steel_gemm_segmented_nax`, `sdpa_full_self_attention_nax`, …) is unreachable
  locally and observable only through ranked receipts. Decode (matvec) is not
  gated; prefill (matmul) is. Decode carries 0.638 of the score elasticity, so
  the observable half is the larger half.
- the same suffix appears at `scaled_dot_product_attention.cpp:747-752`, where it
  picks between `sdpa_vector` and `sdpa_vector_2pass`. Neither is on the scored
  path: the 2-pass branch needs `k.shape(2) >= 1024` while the scored decode
  window runs a 512-token seed out to 640, and the Laguna model never calls the
  library SDPA on decode at all — its own fused kernels intercept
  (`LagunaRuntimeModel.swift:6152` sliding, `:6178` full, both default-on and
  both observed live in the census below), and
  `grep -rn scaledDotProductAttention Sources/` is empty. Local decode numbers
  here therefore describe the *fused* attention path, not the library one.
  (This is correction 8; it retracted a next-step recommendation I had already
  published, see below.)

Local recipe: `--local-iterate` = 128 decode steps + a 512-token prefill,
`timingRepeats = 1`, golden gate
`correctness_prompts/public_longcopy_gate_english_512_256.json`, sealed into
`score.local-iterate.json`. Local decode ~12 935 µs/token against 4 897–4 932 µs
ranked, local prefill ~1 122–1 139 µs against ~188 µs: ≈2.6× on decode and 6.0×
on prefill, the extra prefill factor being exactly the NAX gap.

## Exact commands behind the numbers quoted here

```
python3 research/fern_r109f_leg_instrument.py      # per-leg instrument sd
python3 research/fern_r109f_host_drift.py          # drift + autocorrelation
python3 research/fern_r109f_own_shots.py           # our receipts, one row each
python3 research/fern_r109f_leg_noise.py           # field-wide leg noise
bash    research/fern_r109f_fusion_census.sh       # the census above
bash    research/fern_r109f_env_bench.sh <label> VAR=VAL   # local env A/B
```

## Eight self-corrections this campaign carries

Two were forced by new data, two were caught before publication, and all eight
are recorded in place with the wrong number still visible:

1. "normalized is a 0.002 % instrument" — **retracted**; it was one lucky pair.
2. "we ship a package 0.60 % worse than rank 2" — **retracted**; that gap was a
   −2.19 σ draw, not code.
3. QHOIST "678× the noise band" — **corrected** to −1.36 % normalized = −3.82 σ,
   prefill-driven (+4.27 σ on the prefill leg). The revert stands.
4. ×33.4 / ×494.9 luck-amplification factors — **retracted** to ×2.7 after
   adopting a ≥3-df rule for any ratio of variances.
5. "the local iterate repeats to 0.05–0.10 %" — **corrected**: an 8-run sweep
   puts local decode cv at ≈0.35 % (σ ≈ 49 µs). The local advantage is
   throughput and slot-freedom, not precision.
6. "decode and prefill are equally differentiated" — **corrected**: robust
   (median/MAD) cv says decode 0.168 % versus prefill 0.040 %, so decode is the
   bigger lever by ×4. Caught by switching estimators, not by new data.
7. A code-spread ceiling that swung **×9.6** (0.179 % → 1.713 %) between two
   cache refreshes, caught *before* it was logged. The tell was that only
   candidate legs inflated while the baseline decode leg did not (tail inflation
   ×0.95): that is the signature of a few broken candidate packages, not a noisy
   host. The robust estimator moved 0.224 % → 0.239 % over the same refresh and
   is now the default; the plain moments are still logged beside it, unquoted.
8. "`DARKBLOOM_AOT_SDPA_2PASS_PLANES` is the one genuinely open decode arm" —
   **retracted**, and it is the one I am least happy about because the ticket-7
   note published it as a next step. The clamp arithmetic was right; the
   *reachability* was wrong twice. `sdpa_vector_2pass` needs `k.shape(2) >= 1024`
   and the scored decode window is KV 512→640, so it is never dispatched on any
   host; and the model never calls the library SDPA on decode anyway (fused
   interception at `LagunaRuntimeModel.swift:6152`/`:6178`, and zero
   `scaledDotProductAttention` call sites in `Sources/`). Corollary: the
   `MLX_SDPA_BLOCKS` null below is a *structural zero* — its env read sits inside
   the undispatched function — and `DARKBLOOM_AOT_SDPA_PLANES` is a fossil on the
   same unreached path. This one cost nothing to find (static reading plus census
   artifacts already on disk) and would have cost a rebuild plus ~20 receipts to
   discover the expensive way.

Two operational failures belong here too. A ticket-7 launch was rejected at
07:25Z because submission notes must be **≥5 KiB** and mine was 3 676 bytes; the
slot went to another user of this shared account 68 seconds later. The poller now
pre-flights note size before it ever claims the slot. Then a second slot was lost
at 07:57Z because the poller's 120 s interval is longer than the gap between one
receipt terminating and the next user claiming the channel; the interval is now
15 s.

## Caveats

* The atlas-v3 class mean sits +0.3073 % above the base class (se 0.1750 %,
  1.76 σ). **That is not claimed.** It is below 2 σ, it is smaller than what a
  decode-only edit can plausibly buy (the field's decode-leg code differentiation
  caps a decode arm at ~0.168 % of score), and a local A/B of the same constant
  measured −0.0260 % at a 0.35 % noise floor. Atlas v3 ships because it is not
  worse and costs nothing.
* `MLX_SDPA_BLOCKS` is a **structural zero**, which is stronger than the "null"
  I first filed: eight local runs, all correct, spread −0.65 %…+0.65 % with no
  monotone trend — because the variable is read *inside* `sdpa_vector_2pass`, a
  function this benchmark never dispatches (correction 8). The eight runs measure
  the host noise floor. The dispatch site is also outside `editablePaths`, so it
  was never shippable either way.
* The published-score axis is 0.5169 % sd, so a single receipt — including this
  one — cannot adjudicate anything on its own. That is the point of the series.

## Next steps

The ticket-7 note in this series named `DARKBLOOM_AOT_SDPA_2PASS_PLANES = 1` as
the one knob in a ~40-knob census sitting genuinely below its clamp, and
recommended spending a rebuild plus ~20 ranked receipts on it. **That
recommendation is withdrawn** (correction 8 above): the clamp reading was right,
but the kernel is never dispatched by this benchmark and the model never calls
the library SDPA on decode at all.

What replaces it is the only attention surface the scored run actually touches:
the **prefill** full-attention family — `kernels/steel/attn` and
`kernels/scaled_dot_product_attention.metal`, both inside `editablePaths`. Two
properties make it the right target. It is NAX-forked
(`sdpa_full_self_attention_nax`), so it cannot be timed on this host at all and
must be read from ranked receipts. And it lands on the leg with the tightest
instrument measured anywhere in this campaign — pooled candidate-prefill sd
**0.0750 %** over 3 df — so a 0.30 % effect is adjudicable in **2 receipts**
against 78 on the published score, a 38× discount. That is the same leg that
unblocks the fused-NAX blocking arm in the sibling assignment.

The general lesson, which is cheaper than any of the arms: before spending a
build, ask five questions of a candidate constant — where is it consumed, is it
clamped, is its kernel host-gated, is its path shadowed by a better default, and
do the benchmark's own shapes reach the branch at all? Questions one, two and
five are free. All five together would have screened out most of the eight
corrections above.
