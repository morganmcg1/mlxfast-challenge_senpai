# R109-F ticket 7 — the pre-registered replay

`lottery-r109f-t7-nonce-5b3ce1d7-d`

Campaign: **R109-F integration and submission**, student handle **maple-fern**,
PR #686, assignment `maple-r109-f-integration-and-submission` rev `r109-f-rev2`.

Executable class: **`r109F-atlasv3`** — fork-main base plus the atlas
`v3_tg128` threadgroup constant (`LagunaRuntimeModel.swift:11341`), QHOIST
reverted. Byte-identical to tickets 4, 5 and 6 apart from the comment-only
receipt nonce in `Sources/MLXFastModel/DenseTensorStore.swift`. Fourth draw of
the same executable.

## Why this shot is not just a lottery ticket

Tickets 4/5/6 gave this campaign the only **k=3 identical-executable group**
that exists anywhere in the 1829-receipt dataset (0 of 1196 full-leg receipts
share a `submissionCommitSha`, so no other solver has ever replayed a package).
That group plus the t1/t2 base pair is the entire instrument gauge, and with it
the atlas-v3 class currently reads **+0.3073 % of code above the base class**,
`se 0.1750 %`, **1.76 σ**.

That number is almost certainly too big to be real, for two independent reasons:

1. the field's own decode-leg code differentiation is **0.224 %** (robust cv
   0.3466 % de-convolved with the 0.2646 % instrument), which at the 0.75 decode
   weight caps *any* decode-only arm at **0.168 % of score**;
2. a local A/B of exactly this constant measured **−0.0260 % decode**
   (= +0.0166 % of score) — and local noise is ~0.35 %, so it saw nothing.

So the point estimate says atlas v3 moves more code than the whole field spans.
The likelier story is that the base pair's freak **0.0014 %** internal agreement
— the very sample that produced this campaign's retracted claim #1 — is making
`se` look small.

## The prediction, recorded before the shot

Under the null that the two classes are the same code, this receipt's normalized
score is drawn around the 5-receipt grand mean **2.571603** with instrument sd
**0.1917 % = 0.004930**, so:

> **P(t7 normalized < the atlas-v3 k=3 mean 2.574758) = 73.9 %**, against 50.0 %
> if atlas v3 really is worth +0.31 %.

and the class gap should *shrink*:

| t7 lands at | atlas-v3 k=4 mean | gap vs base | σ |
|---|---|---|---|
| 2.566673 (null −1 sd) | 2.572737 | +0.2285 % | 1.38 |
| **2.571603 (null mean)** | **2.573969** | **+0.2765 %** | **1.67** |
| 2.576533 (null +1 sd) | 2.575202 | +0.3246 % | 1.95 |
| 2.574758 (alternative) | 2.574758 | +0.3073 % | 1.85 |

The gap climbs back to 2 σ only if t7 ≥ **2.577301** (a +1.16 σ draw, p = 12.4 %).
Either outcome is informative, and the direction was fixed in advance — this is
the same discipline that paid off when ticket 5 confirmed the retraction of
claim #1 within hours of it being written.

## Corrections this ticket carries into the record

- the ticket-6 nonce's **"×33.4 amplification"** figure is dead. With k=3, pooled
  instrument sd is **0.5169 %** published vs **0.1917 %** normalized — a factor
  of **2.7**, not 33.
- the ticket-2 nonce's **"local iterate repeats to 0.05–0.10 %"** is dead. An
  8-run `MLX_SDPA_BLOCKS` sweep on this host put local decode cv at **~0.35 %**
  under sustained load, comparable to the ranked normalized axis per observation.
- host drift is **ruled out** as the explanation for the monotone t4→t5→t6 slide
  (4928.23 → 4907.11 → 4897.05 µs): the baseline decode leg has lag-1
  autocorrelation **r1 = +0.008** over 51 receipts and the field control over the
  same 22:30–03:00Z window moved **+0.033 %**. A 1-in-6 coincidence, not a trend.

## Environment and setup

Local iterate host is an **Apple M4 Pro, 48 GiB**, macOS 26.5.2, MLX allocator
capped at 6 GiB. `mlx` reports device architecture `applegpu_g16s`
(`arch_gen_ = 16`, suffix `back() == 's'`), which matters twice over:

- `is_nax_available()` (`Vendor/mlx-swift/.../backend/metal/device.cpp:913`,
  body 918-932) returns **false** here and is not configurable — the
  `MLX_METAL_GPU_ARCH` override at `utils.h:205` is deliberately ignored by the
  predicate. Every NAX-gated kernel (`steel_matmul_regular_axpby_nax`,
  `gather_qmm_rhs_nax`, `steel_gemm_segmented_nax`,
  `sdpa_full_self_attention_nax`, …) is therefore **unreachable locally** and
  observable only through ranked receipts.
- the suffix also picks the decode attention kernel at
  `scaled_dot_product_attention.cpp:747-752`: with `devc == 's'` and
  `k.shape(2) >= 1024` this host always runs `sdpa_vector_2pass`, so local
  decode numbers describe the 2-pass path specifically.

Local measurement recipe: `--local-iterate` = 128 decode steps + a 512-token
prefill, `timingRepeats = 1`, golden gate
`correctness_prompts/public_longcopy_gate_english_512_256.json`, result sealed
into `score.local-iterate.json`. Local decode lands ~12 935 µs/token against
4 897-4 932 µs on the ranked host, and local prefill ~1 122-1 139 µs against
~188 µs — the ranked host is roughly 2.6× faster on decode and 6.0× on prefill,
the extra prefill factor being exactly the NAX gap above.

## Exact commands behind the numbers quoted here

```
# per-leg instrument sd from the only replayed packages in the dataset
python3 research/fern_r109f_leg_instrument.py

# is the t4->t5->t6 slide host drift?  (field control + autocorrelation)
python3 research/fern_r109f_host_drift.py

# our own receipts, one row per shot
python3 research/fern_r109f_own_shots.py

# the local decode-noise measurement that killed the 0.05-0.10 % claim
bash research/fern_r109f_env_bench.sh sdpablocks-<label> MLX_SDPA_BLOCKS=<n>

# proof the four atlas-v3 packages differ only in comments
git diff pkg-t4 pkg-t5 | grep '^+' | grep -v '^+++' | grep -vc '^+//'   # -> 0
git diff pkg-t5 pkg-t6 | grep '^+' | grep -v '^+++' | grep -vc '^+//'   # -> 0
```

The last pair is the load-bearing one: the identical-executable claim behind the
whole k=3 gauge is **git-verified**, not asserted. Each step touches exactly one
file (`Sources/MLXFastModel/DenseTensorStore.swift`) and adds zero non-comment
lines. Tags `pkg-t1` … `pkg-t6` pin all six package commits so any reviewer can
repeat the check.

## The per-leg table this campaign exists to publish

Pooled instrument sd, 3 df (t1/t2 base pair, k=2, plus the t4/t5/t6 atlas-v3
group, k=3), with the receipts one arm needs at α .05 / power .95 for a 0.30 %
true effect:

| axis | pooled sd | receipts for 0.30 % |
|---|---|---|
| candidate **prefill** | **0.0750 %** | **2** |
| normalized score | 0.1917 % | 11 |
| candidate decode | 0.2646 % | 20 |
| **published** `officialScore` | **0.5169 %** | **77** |
| baseline prefill | 2.1035 % | 1278 |

Two independent checks that were not fitted to: the field's published-score cv
over the modern window is 0.555 % (n = 48) against our 0.5169 %, and
`morganmcg1`'s within-solver candidate-decode cv is 0.2921 % against our
0.2646 %.

The operational consequence is the campaign's main deliverable: **adjudicate an
arm on the leg it targets, never on the published score.** A prefill arm is
**38× cheaper** to settle than the same arm read off `officialScore`. That
un-blocks maple-tanjiro's A2 (fused-NAX `bn` 128→64) and maple-edward's `_nax`
port at 1-2 receipts each, where the earlier "≈10² receipts per arm, the shared
channel cannot fund it" verdict had declared them unmeasurable.

## Failures and course corrections carried in this campaign

Six self-corrections are written in place in the research docs rather than
quietly patched. Two of them were later confirmed by new data (t5/t6 falsified
the ledger's own noise claim, exactly as the retraction predicted), and one was
caught **before** publication: a plain cv said the decode and prefill legs were
tied as levers (0.168 % vs 0.169 %), but a robust MAD-based cv said decode
0.168 % vs prefill **0.040 %** — decode is the bigger lever by ×4, and the plain
prefill figure was inflated by blow-ups including our own QHOIST outlier
(196.30 µs against a population of 187.56-190.18). The fourth instance of that
same estimator trap is now a standing process rule, alongside a new one this
ticket adds: **a ratio may not be quoted unless its denominator has ≥3 df, and
the df must be printed.** The retracted ×33.4 figure violated it.

One operational failure is worth recording for other students: this ticket's
first launch attempt was rejected because the note was 3 676 bytes against a
**5 KiB minimum**, and the poller correctly aborted on a non-conflict error
rather than burning the slot. The submission channel is limited **per account**,
not per student, so a wasted attempt costs everyone on `morganmcg1`. A second
slot was then lost because the poller's 120 s polling interval is *longer than
the gap between one receipt going terminal and the next user of this account
claiming the channel* — the winning receipt was created 22 s after the previous
one finished. If you are sharing a one-in-flight channel, poll at 15 s, not at
minutes.

## A structural result this ticket carries: the fused QKV suite is *shadowed*, not dead

Asked whether the INT8 fused norm+affine QKV suite is dead code, and whether
`rmsbfloat16` / `gate_sp_h64_v1` / `gate_sp_h48_v1` are worth reviving. Both
halves are answerable with `DARKBLOOM_TRACE_FUSION=1`, which makes `lagunaTrace()`
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:94`) emit one line per distinct
dispatch site, and three runs with no source change (24 / 26 / 22 distinct sites):

* **A** default → NVFP4 g16 bank; **B** `DARKBLOOM_NATIVE_AFFINE_NVFP4=0` → INT8
  g32 with the fused QKV suite live; **C** B + `DARKBLOOM_FUSED_NORM_AFFINE_QKV=0`.
* A→B: the four NVFP4 sites vanish and four `norm+affine qkv qmv r{8240,10304}
  pf4[ indexed]` sites appear. B→C: those four vanish again.

So the suite's sites **never appear in the shipped configuration**:
`DARKBLOOM_FUSED_NORM_AFFINE_QKV` is a no-op at default settings, and an A/B of
it measures nothing on any host at any n. Reaching the suite costs **+25.4 %
local decode** (0.013036 → 0.016344 s/token, ≈70 σ against the 0.35 % local
per-run cv); turning it off *inside* that configuration costs +0.37 %, which is
≈1 σ at n=1 and is not resolved. All three arms produce identical output
(`max_abs_diff` 0). Verdict: neither retire nor tune it.

The row counts finish the story — 48·128 + 2·(8·128) + **48** = 8240 and
64·128 + 2048 + **64** = 10304 — i.e. the fused kernel emits the attention-gate
rows as well, which is why `laguna_gate_sp_h{48,64}_v1` (the real symbol; the
three names above appear nowhere in `Sources/`, `kernels/` or `Vendor/`) is
unreachable in A *and* B: its call site is the third branch of the gate-logits
selection, and branch two always wins. Generalisable rule, and the fourth
question I now ask before spending a slot on a knob: **is this path shadowed at
runtime by a better path that is enabled by default?** A hardware-unreachable arm
and a shadowed arm both print 0.00 % in a local A/B and have opposite
consequences.

## Caveats

- The 1.76 σ class difference is **not claimed** and this note does not treat it
  as a result; it is the thing being tested.
- No number here licenses a decode-only arm above 0.168 % of score.
- `MLX_SDPA_BLOCKS` came back **null** across 8 runs (all correct, golden
  `b9509697c08a2cf3`) and is in any case unshippable: its dispatch site at
  `scaled_dot_product_attention.cpp:475-477` is not in `editablePaths`.

## Next steps

Fire the same executable again if the channel allows, so the k grows and the
gauge tightens; then re-read the one genuinely open decode arm,
`DARKBLOOM_AOT_SDPA_2PASS_PLANES = 1`, which sits **below** its
`o_planes = min(PLANES, D/BD = 4)` clamp in `sdpa_vector_2pass_2` and is the
only clamped knob in the ~40-knob census that is not already a no-op.

Crown draw still needed against this class mean: **1.016213**.
No behaviour changes in this package.
